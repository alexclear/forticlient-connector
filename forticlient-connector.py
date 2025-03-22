from pywinauto.application import Application
import time
import sys
import traceback

def connect_to_vpn():
    # Connect to the running FortiClient application
    try:
        # Try to connect to the FortiClient window
        print("Attempting to connect to FortiClient application...")
        app = Application(backend="uia").connect(title_re="FortiClient.*", visible_only=False)
        print("Connected to application.")

        # Get the main window with retries and better state management
        print("Attempting to get the main window...")
        main_window = None
        for attempt in range(3):
            try:
                # First get the top window (which might be minimized)
                top_window = app.top_window()

                # If it's minimized, restore it first
                if hasattr(top_window, 'is_minimized') and top_window.is_minimized():
                    print("Window is minimized. Attempting to restore...")
                    top_window.restore()
                    time.sleep(1)  # Give time for restore to complete

                # Now try to find the main window
                main_window = app.window(title_re="FortiClient.*", visible_only=False)
                main_window.set_focus()
                main_window.wait('ready', timeout=15)  # Wait for window to be fully ready

                # Verify UI elements exist before proceeding
                try:
                    main_window.child_window(title="Disconnect", control_type="Button").wait('exists', timeout=10)
                    print("Main window verified with UI elements")
                    break
                except:
                    main_window.child_window(title="Connect", control_type="Button").wait('exists', timeout=10)
                    print("Main window verified with UI elements")
                    break

            except Exception as window_error:
                print(f"Window initialization attempt {attempt+1}/3 failed: {str(window_error)}")
                if attempt == 2:
                    raise RuntimeError("Failed to initialize window after 3 attempts")
                time.sleep(3)
                # Don't kill the app on retry, just try a different approach
                try:
                    # Try to get any window and restore it
                    windows = app.windows(visible_only=False)
                    if windows:
                        for win in windows:
                            try:
                                if hasattr(win, 'restore'):
                                    win.restore()
                                    time.sleep(1)
                                    break
                            except:
                                continue
                except Exception as e:
                    print(f"Error attempting to restore windows: {e}")

        if not main_window:
            raise RuntimeError("Failed to connect to FortiClient window after multiple attempts")

        # Check if already connected
        try:
            disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
            if disconnect_button.exists() and disconnect_button.is_enabled():
                print("VPN is already connected")
                print("VPN connection check completed")
                return app, main_window
        except Exception as e:
            print(f"Error checking connection status: {e}")

        # Only attempt connection if not already connected
        print("Attempting to establish VPN connection...")
        for attempt in range(3):
            try:
                # First check if we're already connected
                if main_window.child_window(title="Disconnect", control_type="Button").exists():
                    print("VPN connection already active")
                    return app, main_window

                # Refresh UI elements
                main_window.restore()
                main_window.set_focus()
                main_window.wait('ready', timeout=10)

                # Get fresh button reference with existence check
                connect_button = main_window.child_window(title="Connect", control_type="Button")
                connect_button.wait('exists enabled visible', timeout=15)

                print(f"Click attempt {attempt + 1}/3")
                connect_button.click()

                # Verify click was successful
                connect_button.wait_not('enabled', timeout=5)
                break
            except Exception as e:
                print(f"Connect attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:
                    raise
                time.sleep(2)

        print("VPN connection initiated")
        return app, main_window

    except Exception as e:
        print(f"\nCRITICAL ERROR: {type(e).__name__} occurred during connection")
        print(f"Detailed error: {str(e)}")
        print("Last known state:")
        print("- Application object:", 'exists' if 'app' in locals() else 'not found')
        print("- Main window:", 'exists' if 'main_window' in locals() and main_window else 'not found')
        print("\nFull traceback:")
        traceback.print_exc()
        print("\nTroubleshooting tips:")
        print("1. Ensure FortiClient is running and visible")
        print("2. Check the window title matches 'FortiClient' exactly")
        print("3. Try manually interacting with the window once")
        return None, None

def monitor_vpn_connection(app, main_window, check_interval=60):
    """
    Monitor VPN connection and reconnect if disconnected.
    check_interval: time in seconds between connection checks
    """
    print(f"Starting VPN connection monitoring. Checking every {check_interval} seconds...")

    while True:
        try:
            # Get window reference without making it active
            main_window = app.window(title_re="FortiClient.*", visible_only=False)

            # First, check if window is minimized - this requires restoration
            need_to_set_focus = False
            need_to_click_connect = False

            if hasattr(main_window, 'is_minimized') and main_window.is_minimized():
                print("Window is minimized, restoring for status check...")
                main_window.restore()
                time.sleep(1)  # Give time for the UI to stabilize
                # We generally need to set focus after restoring from minimized state
                need_to_set_focus = True

            # Try to check status without setting focus first (unless window was minimized)
            if not need_to_set_focus:
                try:
                    # First check for Disconnect button indicating connection
                    disconnect_button_exists = False
                    connect_button_exists = False
                    disconnect_button_enabled = False
                    connect_button_enabled = False

                    try:
                        disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
                        disconnect_button_exists = disconnect_button.exists()
                        if disconnect_button_exists:
                            disconnect_button_enabled = disconnect_button.is_enabled()
                            print(f"Disconnect button state: exists={disconnect_button_exists}, enabled={disconnect_button_enabled}")
                        else:
                            print("Disconnect button not found (without focus)")
                    except Exception as disc_err:
                        print(f"Error checking Disconnect button: {disc_err}")

                    try:
                        connect_button = main_window.child_window(title="Connect", control_type="Button")
                        connect_button_exists = connect_button.exists()
                        if connect_button_exists:
                            connect_button_enabled = connect_button.is_enabled()
                            print(f"Connect button state: exists={connect_button_exists}, enabled={connect_button_enabled}")
                        else:
                            print("Connect button not found (without focus)")
                    except Exception as conn_err:
                        print(f"Error checking Connect button: {conn_err}")

                    # Determine status based on button states
                    if disconnect_button_exists and disconnect_button_enabled:
                        print("VPN connection is active (checked without focus)")
                    elif connect_button_exists and connect_button_enabled:
                        print("VPN appears to be disconnected. Need to reconnect...")
                        need_to_click_connect = True
                        need_to_set_focus = True  # Need focus to click
                    else:
                        # More detailed diagnostics for unclear status
                        status_details = []
                        if disconnect_button_exists and not disconnect_button_enabled:
                            status_details.append("Disconnect button exists but is disabled")
                        if connect_button_exists and not connect_button_enabled:
                            status_details.append("Connect button exists but is disabled")
                        if not disconnect_button_exists and not connect_button_exists:
                            status_details.append("Neither Connect nor Disconnect buttons found")

                        if not status_details:
                            status_details.append("Unknown UI state")

                        print(f"VPN status unclear (without focus): {', '.join(status_details)}")
                        need_to_set_focus = True  # Need focus to verify
                except Exception as e:
                    print(f"Non-focused status check failed: {e}")
                    print(f"Error type: {type(e).__name__}, detailed error info: {str(e)}")
                    need_to_set_focus = True  # Exception means we need focus to verify

            # Only set focus if we determined it's necessary
            if need_to_set_focus:
                print("Setting focus to interact with the window...")
                main_window.set_focus()
                main_window.wait('visible', timeout=10)

                # Check status again with focus
                try:
                    disconnect_button_exists = False
                    connect_button_exists = False

                    try:
                        disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
                        disconnect_button_exists = disconnect_button.exists()
                        disconnect_button_enabled = disconnect_button.is_enabled() if disconnect_button_exists else False
                        print(f"With focus - Disconnect button state: exists={disconnect_button_exists}, enabled={disconnect_button_enabled}")
                    except Exception as disc_err:
                        print(f"With focus - Error checking Disconnect button: {disc_err}")

                    try:
                        connect_button = main_window.child_window(title="Connect", control_type="Button")
                        connect_button_exists = connect_button.exists()
                        connect_button_enabled = connect_button.is_enabled() if connect_button_exists else False
                        print(f"With focus - Connect button state: exists={connect_button_exists}, enabled={connect_button_enabled}")
                    except Exception as conn_err:
                        print(f"With focus - Error checking Connect button: {conn_err}")

                    if disconnect_button_exists and disconnect_button_enabled:
                        print("VPN connection is active (confirmed with focus)")
                    elif connect_button_exists and connect_button_enabled:
                        print("Clicking Connect button to establish VPN connection...")
                        connect_button.click()
                        print("Reconnect attempt initiated")
                    else:
                        # More detailed diagnostics
                        status_details = []
                        if disconnect_button_exists and not disconnect_button_enabled:
                            status_details.append("Disconnect button exists but is disabled")
                        if connect_button_exists and not connect_button_enabled:
                            status_details.append("Connect button exists but is disabled")
                        if not disconnect_button_exists and not connect_button_exists:
                            status_details.append("Neither Connect nor Disconnect buttons found")

                        if not status_details:
                            status_details.append("Unknown UI state")

                        print(f"VPN status unclear (with focus): {', '.join(status_details)}")
                except Exception as focused_error:
                    print(f"Error checking status with focus: {focused_error}")
                    print(f"Error type: {type(focused_error).__name__}, detailed error: {str(focused_error)}")

            time.sleep(check_interval)

        except Exception as e:
            print(f"Error in monitoring: {e}")
            print(f"Error type: {type(e).__name__}, traceback:")
            traceback.print_exc()
            # If we lost connection to the FortiClient window, try to reconnect
            try:
                print("Attempting to reconnect to FortiClient application...")
                app = Application(backend="uia").connect(title_re="FortiClient.*", visible_only=False)

                # Get the top window and restore if minimized
                top_window = app.top_window()
                if hasattr(top_window, 'is_minimized') and top_window.is_minimized():
                    top_window.restore()
                    time.sleep(1)

                main_window = app.window(title_re="FortiClient.*", visible_only=False)
                print("Reconnected to FortiClient window")
            except Exception as reconnect_error:
                print(f"Failed to reconnect to FortiClient window: {reconnect_error}")
                print(f"Will retry in {check_interval} seconds...")

            time.sleep(check_interval)

# Main execution
if __name__ == "__main__":
    app, main_window = connect_to_vpn()
    if app and main_window:
        # Start monitoring after initial connection
        monitor_vpn_connection(app, main_window)
    else:
        print("Failed to connect to VPN. Cannot start monitoring.")
