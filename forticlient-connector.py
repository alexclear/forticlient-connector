from pywinauto.application import Application
import time
import sys
import traceback

def connect_to_vpn():
    # Connect to the running FortiClient application
    try:
        # Try to connect to the FortiClient window
        print("Attempting to connect to FortiClient application...")
        app = Application(backend="uia").connect(title_re="FortiClient.*")
        print("Connected to application.")

        # Get the main window
        print("Attempting to get the main window...")
        main_window = app.window(title_re="FortiClient.*")
        print("Main window retrieved.")

        # Click the Connect button
        print("Attempting to click the Connect button...")
        connect_button = main_window.child_window(title="Connect", control_type="Button")
        connect_button.click()

        print("VPN connection initiated")
        return app, main_window

    except Exception as e:
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("Traceback:")
        traceback.print_exc()
        return None, None

def monitor_vpn_connection(app, main_window, check_interval=60):
    """
    Monitor VPN connection and reconnect if disconnected.
    check_interval: time in seconds between connection checks
    """
    print(f"Starting VPN connection monitoring. Checking every {check_interval} seconds...")
    
    while True:
        try:
            # For FortiClient, we can check for the presence of the "Connect" button
            # If it's enabled/visible, it likely means we're disconnected
            try:
                # First check for Disconnect button indicating connection
                disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
                if disconnect_button.exists() and disconnect_button.is_enabled():
                    print("VPN connection appears to be active")
                else:
                    # Check Connect button if Disconnect isn't present/enabled
                    connect_button = main_window.child_window(title="Connect", control_type="Button")
                    if connect_button.is_enabled():
                        print("VPN appears to be disconnected. Attempting to reconnect...")
                        connect_button.click()
                        print("Reconnect attempt initiated")
                    else:
                        print("VPN status is unclear, possibly connecting...")
            except Exception as button_error:
                print(f"Error checking connection status: {button_error}")
                # This might indicate we're connected (button not present) or another issue
                
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"Error in monitoring: {e}")
            # If we lost connection to the FortiClient window, try to reconnect
            try:
                print("Attempting to reconnect to FortiClient application...")
                app = Application(backend="uia").connect(title_re="FortiClient.*")
                main_window = app.window(title_re="FortiClient.*")
                print("Reconnected to FortiClient window")
            except Exception as reconnect_error:
                print(f"Failed to reconnect to FortiClient window: {reconnect_error}")
                print("Will retry in {check_interval} seconds...")
            
            time.sleep(check_interval)

# Main execution
if __name__ == "__main__":
    app, main_window = connect_to_vpn()
    if app and main_window:
        # Start monitoring after initial connection
        monitor_vpn_connection(app, main_window)
    else:
        print("Failed to connect to VPN. Cannot start monitoring.")
