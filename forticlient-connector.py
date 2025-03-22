from pywinauto.application import Application
import time
import sys
import traceback
from datetime import datetime

def get_timestamp():
    """Return a formatted timestamp string in [MM/DD/YYYY HH:MM:SSam/pm] format"""
    now = datetime.now()
    return now.strftime("[%m/%d/%Y %I:%M:%S%p]")

def log_message(message):
    """Print a message with a timestamp prefix"""
    print(f"{get_timestamp()} {message}")

def connect_to_vpn():
    # Connect to the running FortiClient application
    try:
        # Try to connect to the FortiClient window
        log_message("Attempting to connect to FortiClient application...")
        app = Application(backend="uia").connect(title_re="FortiClient.*", visible_only=False)
        log_message("Connected to application.")

        # Get the main window with retries and better state management
        log_message("Attempting to get the main window...")
        main_window = None
        for attempt in range(3):
            try:
                # First get the top window (which might be minimized)
                top_window = app.top_window()

                # If it's minimized, restore it first
                if hasattr(top_window, 'is_minimized') and top_window.is_minimized():
                    log_message("Window is minimized. Attempting to restore...")
                    top_window.restore()
                    time.sleep(1)  # Give time for restore to complete

                # Now try to find the main window
                main_window = app.window(title_re="FortiClient.*", visible_only=False)
                main_window.set_focus()
                main_window.wait('ready', timeout=15)  # Wait for window to be fully ready

                # Verify UI elements exist before proceeding
                try:
                    main_window.child_window(title="Disconnect", control_type="Button").wait('exists', timeout=10)
                    log_message("Main window verified with UI elements")
                    break
                except:
                    main_window.child_window(title="Connect", control_type="Button").wait('exists', timeout=10)
                    log_message("Main window verified with UI elements")
                    break

            except Exception as window_error:
                log_message(f"Window initialization attempt {attempt+1}/3 failed: {str(window_error)}")
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
                    log_message(f"Error attempting to restore windows: {e}")

        if not main_window:
            raise RuntimeError("Failed to connect to FortiClient window after multiple attempts")

        # Check if already connected
        try:
            disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
            if disconnect_button.exists() and disconnect_button.is_enabled():
                log_message("VPN is already connected")
                log_message("VPN connection check completed")
                return app, main_window
        except Exception as e:
            log_message(f"Error checking connection status: {e}")

        # Only attempt connection if not already connected
        log_message("Attempting to establish VPN connection...")
        for attempt in range(3):
            try:
                # First check if we're already connected
                if main_window.child_window(title="Disconnect", control_type="Button").exists():
                    log_message("VPN connection already active")
                    return app, main_window

                # Refresh UI elements
                main_window.restore()
                main_window.set_focus()
                main_window.wait('ready', timeout=10)

                # Get fresh button reference with existence check
                connect_button = main_window.child_window(title="Connect", control_type="Button")
                connect_button.wait('exists enabled visible', timeout=15)

                log_message(f"Click attempt {attempt + 1}/3")
                connect_button.click()

                # Verify click was successful
                connect_button.wait_not('enabled', timeout=5)
                break
            except Exception as e:
                log_message(f"Connect attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:
                    raise
                time.sleep(2)

        log_message("VPN connection initiated")
        return app, main_window

    except Exception as e:
        log_message(f"\nCRITICAL ERROR: {type(e).__name__} occurred during connection")
        log_message(f"Detailed error: {str(e)}")
        log_message("Last known state:")
        log_message("- Application object: " + ('exists' if 'app' in locals() else 'not found'))
        log_message("- Main window: " + ('exists' if 'main_window' in locals() and main_window else 'not found'))
        log_message("\nFull traceback:")
        traceback_lines = traceback.format_exc().splitlines()
        for line in traceback_lines:
            log_message(line)
        log_message("\nTroubleshooting tips:")
        log_message("1. Ensure FortiClient is running and visible")
        log_message("2. Check the window title matches 'FortiClient' exactly")
        log_message("3. Try manually interacting with the window once")
        return None, None

def monitor_vpn_connection(app, main_window, check_interval=60):
    """
    Monitor VPN connection and reconnect if disconnected.
    check_interval: time in seconds between connection checks
    """
    log_message(f"Starting VPN connection monitoring. Checking every {check_interval} seconds...")

    while True:
        try:
            # Get window reference without making it active
            main_window = app.window(title_re="FortiClient.*", visible_only=False)

            # First, check if window is minimized - this requires restoration
            need_to_set_focus = False
            need_to_click_connect = False

            if hasattr(main_window, 'is_minimized') and main_window.is_minimized():
                log_message("Window is minimized, restoring for status check...")
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
                            log_message(f"Disconnect button state: exists={disconnect_button_exists}, enabled={disconnect_button_enabled}")
                        else:
                            log_message("Disconnect button not found (without focus)")
                    except Exception as disc_err:
                        log_message(f"Error checking Disconnect button: {disc_err}")

                    try:
                        connect_button = main_window.child_window(title="Connect", control_type="Button")
                        connect_button_exists = connect_button.exists()
                        if connect_button_exists:
                            connect_button_enabled = connect_button.is_enabled()
                            log_message(f"Connect button state: exists={connect_button_exists}, enabled={connect_button_enabled}")
                        else:
                            log_message("Connect button not found (without focus)")
                    except Exception as conn_err:
                        log_message(f"Error checking Connect button: {conn_err}")

                    # Determine status based on button states
                    if disconnect_button_exists and disconnect_button_enabled:
                        log_message("VPN connection is active (checked without focus)")
                    elif connect_button_exists and connect_button_enabled:
                        log_message("VPN appears to be disconnected. Need to reconnect...")
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

                        log_message(f"VPN status unclear (without focus): {', '.join(status_details)}")
                        need_to_set_focus = True  # Need focus to verify
                except Exception as e:
                    log_message(f"Non-focused status check failed: {e}")
                    log_message(f"Error type: {type(e).__name__}, detailed error info: {str(e)}")
                    need_to_set_focus = True  # Exception means we need focus to verify

            # Only set focus if we determined it's necessary
            if need_to_set_focus:
                log_message("Setting focus to interact with the window...")
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
                        log_message(f"With focus - Disconnect button state: exists={disconnect_button_exists}, enabled={disconnect_button_enabled}")
                    except Exception as disc_err:
                        log_message(f"With focus - Error checking Disconnect button: {disc_err}")

                    try:
                        connect_button = main_window.child_window(title="Connect", control_type="Button")
                        connect_button_exists = connect_button.exists()
                        connect_button_enabled = connect_button.is_enabled() if connect_button_exists else False
                        log_message(f"With focus - Connect button state: exists={connect_button_exists}, enabled={connect_button_enabled}")
                    except Exception as conn_err:
                        log_message(f"With focus - Error checking Connect button: {conn_err}")

                    if disconnect_button_exists and disconnect_button_enabled:
                        log_message("VPN connection is active (confirmed with focus)")
                    elif connect_button_exists and connect_button_enabled:
                        log_message("Clicking Connect button to establish VPN connection...")
                        connect_button.click()
                        log_message("Reconnect attempt initiated")
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

                        log_message(f"VPN status unclear (with focus): {', '.join(status_details)}")
                except Exception as focused_error:
                    log_message(f"Error checking status with focus: {focused_error}")
                    log_message(f"Error type: {type(focused_error).__name__}, detailed error: {str(focused_error)}")

            time.sleep(check_interval)

        except Exception as e:
            log_message(f"Error in monitoring: {e}")
            log_message(f"Error type: {type(e).__name__}, traceback:")
            traceback_lines = traceback.format_exc().splitlines()
            for line in traceback_lines:
                log_message(line)
            # If we lost connection to the FortiClient window, try to reconnect
            try:
                log_message("Attempting to reconnect to FortiClient application...")
                app = Application(backend="uia").connect(title_re="FortiClient.*", visible_only=False)

                # Get the top window and restore if minimized
                top_window = app.top_window()
                if hasattr(top_window, 'is_minimized') and top_window.is_minimized():
                    top_window.restore()
                    time.sleep(1)

                main_window = app.window(title_re="FortiClient.*", visible_only=False)
                log_message("Reconnected to FortiClient window")
            except Exception as reconnect_error:
                log_message(f"Failed to reconnect to FortiClient window: {reconnect_error}")
                log_message(f"Will retry in {check_interval} seconds...")

            time.sleep(check_interval)

# Main execution
if __name__ == "__main__":
    log_message("Starting FortiClient connector script")
    app, main_window = connect_to_vpn()
    if app and main_window:
        # Start monitoring after initial connection
        monitor_vpn_connection(app, main_window)
    else:
        log_message("Failed to connect to VPN. Cannot start monitoring.")
