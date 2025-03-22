from pywinauto.application import Application
import time
import sys
import traceback
from datetime import datetime
import re

# Configuration
ALWAYS_SET_FOCUS = False  # Set to True if elements are consistently not found without focus
DEBUG_UI_INFO = True      # Set to True for additional UI debugging information
USE_TEXT_DETECTION = True # Use text content analysis for status detection
CACHE_DURATION = 30      # How long to trust cached status (seconds)

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

def dump_window_info(window):
    """Debug helper to dump window hierarchy info"""
    if not DEBUG_UI_INFO:
        return

    log_message("--- Window Debug Information ---")
    try:
        log_message(f"Window title: {window.window_text()}")

        # Safely get properties using getattr with defaults
        try:
            control_type = "Unknown"
            if hasattr(window, 'control_type'):
                if callable(getattr(window, 'control_type')):
                    control_type = window.control_type()
                else:
                    control_type = getattr(window, 'control_type', "Unknown")
            log_message(f"Control type: {control_type}")
        except Exception as e:
            log_message(f"Error getting control type: {e}")
    
        try:
            rectangle = "Unknown"
            if hasattr(window, 'rectangle'):
                if callable(getattr(window, 'rectangle')):
                    rectangle = window.rectangle()
                else:
                    rectangle = getattr(window, 'rectangle', "Unknown")
            log_message(f"Rectangle: {rectangle}")
        except Exception as e:
            log_message(f"Error getting rectangle: {e}")

        try:
            visible = "Unknown"
            if hasattr(window, 'is_visible'):
                if callable(getattr(window, 'is_visible')):
                    visible = window.is_visible()
                else:
                    visible = getattr(window, 'is_visible', "Unknown")
            log_message(f"Visible: {visible}")
        except Exception as e:
            log_message(f"Error getting visibility: {e}")

        log_message("Child controls:")
        try:
            if hasattr(window, 'children') and callable(window.children):
                all_children = window.children()
                if not all_children:
                    log_message("  No children found")
                else:
                    for idx, child in enumerate(all_children):
                        try:
                            # Safely get child info
                            child_type = "Unknown"
                            try:
                                if hasattr(child, 'control_type') and callable(getattr(child, 'control_type')):
                                    child_type = child.control_type()
                            except:
                                pass

                            child_text = "No text"
                            try:
                                if hasattr(child, 'window_text') and callable(getattr(child, 'window_text')):
                                    child_text = child.window_text()
                                    # Truncate long texts for readability
                                    if len(child_text) > 80:
                                        child_text = child_text[:77] + "..."
                            except:
                                pass

                            child_visible = "Unknown"
                            try:
                                if hasattr(child, 'is_visible') and callable(getattr(child, 'is_visible')):
                                    child_visible = child.is_visible()
                            except:
                                pass

                            log_message(f"  {idx}: {child_type} - '{child_text}' (visible: {child_visible})")
                        except Exception as child_err:
                            log_message(f"  {idx}: Error getting info: {child_err}")
            else:
                log_message("  Children property not available or not callable")
        except Exception as children_err:
            log_message(f"Error enumerating children: {children_err}")
    except Exception as e:
        log_message(f"Error dumping window info: {e}")
    log_message("--- End Window Debug Information ---")

def find_button_in_text(window, button_text):
    """Attempt to find a button by searching for its text in child elements"""
    button_found = False
    button_enabled = False

    try:
        # First try standard approach
        button = window.child_window(title=button_text, control_type="Button")
        if button.exists():
            return True, button.is_enabled()
    except:
        pass  # Fall through to text-based search

    # Search all child controls for text content containing the button name
    try:
        all_children = window.children()
        for child in all_children:
            try:
                child_text = child.window_text() if hasattr(child, 'window_text') and callable(child.window_text) else ""
                if button_text in child_text:
                    # Found text containing the button name
                    button_found = True
                    # Check if it appears to be enabled (heuristic)
                    button_enabled = True  # Assume enabled if found
                    break

                # Also check for elements with matching text in their descendants
                if hasattr(child, 'descendants') and callable(child.descendants):
                    for desc in child.descendants():
                        try:
                            desc_text = desc.window_text() if hasattr(desc, 'window_text') and callable(desc.window_text) else ""
                            if button_text in desc_text:
                                button_found = True
                                button_enabled = True  # Assume enabled if found
                                break
                        except:
                            continue
                    if button_found:
                        break
            except:
                continue
    except:
        pass

    return button_found, button_enabled

def get_window_full_text(window, with_focus=False):
    """Extract all text from window and its children"""
    texts = []
    
    # Try multiple methods to get text content
    try:
        # Method 1: Direct window text
        if hasattr(window, 'window_text') and callable(window.window_text):
            window_text = window.window_text()
            if window_text:
                texts.append(window_text)
    except Exception as e:
        if DEBUG_UI_INFO:
            log_message(f"Error getting window text: {e}")

    # Method 2: Get text from all child elements
    try:
        if hasattr(window, 'children') and callable(window.children):
            for child in window.children():
                try:
                    if hasattr(child, 'window_text') and callable(child.window_text):
                        child_text = child.window_text()
                        if child_text:
                            texts.append(child_text)

                    # For blank children with children of their own (common in some UIs)
                    if hasattr(child, 'children') and callable(child.children):
                        for grandchild in child.children():
                            try:
                                if hasattr(grandchild, 'window_text') and callable(grandchild.window_text):
                                    gc_text = grandchild.window_text()
                                    if gc_text:
                                        texts.append(gc_text)
                            except:
                                pass
                except:
                    pass
    except Exception as e:
        if DEBUG_UI_INFO:
            log_message(f"Error getting child texts: {e}")

    # Method 3: Use descendants() if available (gets all nested elements)
    try:
        if hasattr(window, 'descendants') and callable(window.descendants):
            for desc in window.descendants():
                try:
                    if hasattr(desc, 'window_text') and callable(desc.window_text):
                        desc_text = desc.window_text()
                        if desc_text:
                            texts.append(desc_text)
                except:
                    pass
    except Exception as e:
        if DEBUG_UI_INFO:
            log_message(f"Error getting descendant texts: {e}")

    # Method 4: Try to get printable_tree if available (used by pywinauto for debugging)
    try:
        if hasattr(window, 'print_control_identifiers'):
            tree_text = str(window.print_control_identifiers())
            if tree_text:
                texts.append(tree_text)
    except:
        pass

    # Combine all the text we found
    full_text = " ".join(texts)
    
    if DEBUG_UI_INFO and not full_text and not with_focus:
        log_message("WARNING: No text content extracted from window. Text detection may fail.")
    
    return full_text

def analyze_vpn_status_from_text(text):
    """Analyze window text to determine VPN status"""
    if not text:
        return None, "No window text found"

    # Positive indicators that VPN is connected
    connected_indicators = [
        "VPN Connected",
        "Disconnect",       # Disconnect button present
        "Duration",         # Duration field indicates active connection
        "Bytes Received", 
        "Bytes Sent",
        "IP Address",       # Connected VPNs typically show the assigned IP
        "Username"          # Connected VPNs typically show the username
    ]

    # Indicators that VPN is disconnected
    disconnected_indicators = [
        "Not Connected",
        "VPN Disconnected",
        "Connect"           # Connect button present
    ]

    # Check for connection indicators
    found_connected = []
    for indicator in connected_indicators:
        if indicator in text:
            found_connected.append(indicator)

    # Check for disconnection indicators
    found_disconnected = []
    for indicator in disconnected_indicators:
        if indicator in text:
            found_disconnected.append(indicator)

    # Analyze findings
    if found_connected and not found_disconnected:
        return True, f"Connected - indicators found: {', '.join(found_connected)}"
    elif found_disconnected and not found_connected:
        return False, f"Disconnected - indicators found: {', '.join(found_disconnected)}"
    elif found_connected and found_disconnected:
        # If both types of indicators are found, prioritize connected ones
        # This is because "Connect" might appear in the UI even when connected
        
        # Strong indicators of connection
        strong_indicators = ["VPN Connected", "Duration", "Bytes Received", "IP Address", "Username"]
        found_strong = [i for i in strong_indicators if i in found_connected]
        
        if found_strong:
            return True, f"Likely connected despite mixed indicators: connected={found_connected}, disconnected={found_disconnected}"
        else:
            return None, f"Ambiguous status: connected={found_connected}, disconnected={found_disconnected}"
    else:
        return None, "No clear VPN status indicators found"

def monitor_vpn_connection(app, main_window, check_interval=60):
    """
    Monitor VPN connection and reconnect if disconnected.
    check_interval: time in seconds between connection checks
    """
    global ALWAYS_SET_FOCUS

    log_message(f"Starting VPN connection monitoring. Checking every {check_interval} seconds...")
    consecutive_focus_needed = 0
    max_consecutive_focus = 3  # After this many failures, always use focus
    
    # Status caching to reduce focus operations
    last_known_status = None  # None=unknown, True=connected, False=disconnected
    last_status_time = 0
    last_status_with_focus = False  # Whether the last status check required focus

    while True:
        try:
            # Get window reference without making it active
            main_window = app.window(title_re="FortiClient.*", visible_only=False)

            # First, check if window is minimized - this requires restoration
            need_to_set_focus = ALWAYS_SET_FOCUS  # Use the global setting
            need_to_click_connect = False

            # Check if we can use cached status
            current_time = time.time()
            status_age = current_time - last_status_time
            
            if last_known_status is True and status_age < CACHE_DURATION:
                log_message(f"Using cached VPN status (connected, age: {int(status_age)}s)")
                time.sleep(check_interval)
                continue

            if hasattr(main_window, 'is_minimized') and main_window.is_minimized():
                log_message("Window is minimized, restoring for status check...")
                main_window.restore()
                time.sleep(1)  # Give time for the UI to stabilize
                # We generally need to set focus after restoring from minimized state
                need_to_set_focus = True
                consecutive_focus_needed = 0  # Reset counter after manual intervention

            # Try to check status without setting focus first (unless window was minimized or always focus)
            if not need_to_set_focus:
                try:
                    # Debug window hierarchy if enabled
                    dump_window_info(main_window)

                    # First try using text-based detection if configured
                    if USE_TEXT_DETECTION:
                        full_text = get_window_full_text(main_window)
                        text_status, text_details = analyze_vpn_status_from_text(full_text)
                        
                        if text_status is True:
                            log_message(f"Text analysis indicates VPN is connected: {text_details}")
                            log_message("VPN connection is active (text analysis without focus)")
                            consecutive_focus_needed = 0  # Reset counter
                            # Update cache
                            last_known_status = True
                            last_status_time = current_time
                            last_status_with_focus = False
                            time.sleep(check_interval)
                            continue
                        elif text_status is False:
                            log_message(f"Text analysis indicates VPN is disconnected: {text_details}")
                            need_to_click_connect = True
                            need_to_set_focus = True  # Need focus to click connect
                            # Update cache
                            last_known_status = False
                            last_status_time = current_time
                            last_status_with_focus = False
                        else:
                            log_message(f"Text analysis is inconclusive: {text_details}")
                            # Fall through to button detection
                    
                    # If text detection was inconclusive or not used, check buttons
                    disconnect_button_exists = False
                    connect_button_exists = False
                    disconnect_button_enabled = False
                    connect_button_enabled = False

                    # Try standard approach first
                    try:
                        disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
                        disconnect_button_exists = disconnect_button.exists()
                        if disconnect_button_exists:
                            disconnect_button_enabled = disconnect_button.is_enabled()
                            log_message(f"Disconnect button state: exists={disconnect_button_exists}, enabled={disconnect_button_enabled}")
                        else:
                            log_message("Disconnect button not found with standard method (without focus)")
                            # Try text-based search
                            text_found, text_enabled = find_button_in_text(main_window, "Disconnect")
                            if text_found:
                                log_message(f"Disconnect text found in window content, likely enabled={text_enabled}")
                                disconnect_button_exists = True
                                disconnect_button_enabled = text_enabled
                            else:
                                log_message("Disconnect button not found (without focus)")
                    except Exception as disc_err:
                        log_message(f"Error checking Disconnect button: {disc_err}")
                        # Try text-based search as fallback
                        text_found, text_enabled = find_button_in_text(main_window, "Disconnect")
                        if text_found:
                            log_message(f"Disconnect text found in window content, likely enabled={text_enabled}")
                            disconnect_button_exists = True
                            disconnect_button_enabled = text_enabled

                    try:
                        connect_button = main_window.child_window(title="Connect", control_type="Button")
                        connect_button_exists = connect_button.exists()
                        if connect_button_exists:
                            connect_button_enabled = connect_button.is_enabled()
                            log_message(f"Connect button state: exists={connect_button_exists}, enabled={connect_button_enabled}")
                        else:
                            log_message("Connect button not found with standard method (without focus)")
                            # Try text-based search
                            text_found, text_enabled = find_button_in_text(main_window, "Connect")
                            if text_found:
                                log_message(f"Connect text found in window content, likely enabled={text_enabled}")
                                connect_button_exists = True
                                connect_button_enabled = text_enabled
                            else:
                                log_message("Connect button not found (without focus)")
                    except Exception as conn_err:
                        log_message(f"Error checking Connect button: {conn_err}")
                        # Try text-based search as fallback
                        text_found, text_enabled = find_button_in_text(main_window, "Connect")
                        if text_found:
                            log_message(f"Connect text found in window content, likely enabled={text_enabled}")
                            connect_button_exists = True
                            connect_button_enabled = text_enabled

                    # Determine status based on button states
                    if disconnect_button_exists and disconnect_button_enabled:
                        log_message("VPN connection is active (checked without focus)")
                        consecutive_focus_needed = 0  # Reset counter on success
                        # Update cache
                        last_known_status = True
                        last_status_time = current_time
                        last_status_with_focus = False
                    elif connect_button_exists and connect_button_enabled:
                        log_message("VPN appears to be disconnected. Need to reconnect...")
                        need_to_click_connect = True
                        need_to_set_focus = True  # Need focus to click
                        consecutive_focus_needed = 0  # Reset counter as we found something
                        # Update cache
                        last_known_status = False
                        last_status_time = current_time
                        last_status_with_focus = False
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
                        consecutive_focus_needed += 1
                        log_message(f"Failed to determine status without focus {consecutive_focus_needed} time(s) in a row")

                        # If we repeatedly need focus, update the global setting
                        if consecutive_focus_needed >= max_consecutive_focus and not ALWAYS_SET_FOCUS:
                            log_message("Setting ALWAYS_SET_FOCUS=True due to consistent focus requirements")
                            ALWAYS_SET_FOCUS = True
                            
                        # Don't update cache for unclear status
                except Exception as e:
                    log_message(f"Non-focused status check failed: {e}")
                    log_message(f"Error type: {type(e).__name__}, detailed error info: {str(e)}")
                    need_to_set_focus = True  # Exception means we need focus to verify
                    consecutive_focus_needed += 1

            # Only set focus if we determined it's necessary
            if need_to_set_focus:
                log_message("Setting focus to interact with the window...")
                main_window.set_focus()
                main_window.wait('visible', timeout=10)

                # Debug window hierarchy after setting focus if enabled
                dump_window_info(main_window)

                # First try text-based detection with focus
                if USE_TEXT_DETECTION:
                    full_text = get_window_full_text(main_window, with_focus=True)
                    text_status, text_details = analyze_vpn_status_from_text(full_text)
                    
                    if text_status is True:
                        log_message(f"With focus - Text analysis indicates VPN is connected: {text_details}")
                        # Update cache
                        last_known_status = True
                        last_status_time = current_time
                        last_status_with_focus = True
                    elif text_status is False:
                        log_message(f"With focus - Text analysis indicates VPN is disconnected: {text_details}")
                        need_to_click_connect = True
                        # Update cache
                        last_known_status = False
                        last_status_time = current_time
                        last_status_with_focus = True
                    else:
                        log_message(f"With focus - Text analysis is inconclusive: {text_details}")

                # Check status with button detection (with focus)
                try:
                    disconnect_button_exists = False
                    connect_button_exists = False
                    disconnect_button = None
                    connect_button = None

                    try:
                        disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
                        disconnect_button_exists = disconnect_button.exists()
                        disconnect_button_enabled = disconnect_button.is_enabled() if disconnect_button_exists else False
                        log_message(f"With focus - Disconnect button state: exists={disconnect_button_exists}, enabled={disconnect_button_enabled}")
                    except Exception as disc_err:
                        log_message(f"With focus - Error checking Disconnect button: {disc_err}")
                        # Try text-based search as fallback
                        text_found, text_enabled = find_button_in_text(main_window, "Disconnect")
                        if text_found:
                            log_message(f"With focus - Disconnect text found in window content, likely enabled={text_enabled}")
                            disconnect_button_exists = True
                            disconnect_button_enabled = text_enabled

                    try:
                        connect_button = main_window.child_window(title="Connect", control_type="Button")
                        connect_button_exists = connect_button.exists()
                        connect_button_enabled = connect_button.is_enabled() if connect_button_exists else False
                        log_message(f"With focus - Connect button state: exists={connect_button_exists}, enabled={connect_button_enabled}")
                    except Exception as conn_err:
                        log_message(f"With focus - Error checking Connect button: {conn_err}")
                        # Try text-based search as fallback
                        text_found, text_enabled = find_button_in_text(main_window, "Connect")
                        if text_found:
                            log_message(f"With focus - Connect text found in window content, likely enabled={text_enabled}")
                            connect_button_exists = True
                            connect_button_enabled = text_enabled

                    # Determine final state and take action
                    if disconnect_button_exists and disconnect_button_enabled:
                        log_message("VPN connection is active (confirmed with focus)")
                        # Update cache
                        last_known_status = True
                        last_status_time = current_time
                        last_status_with_focus = True
                    elif connect_button_exists and connect_button_enabled and connect_button is not None:
                        log_message("Clicking Connect button to establish VPN connection...")
                        connect_button.click()
                        log_message("Reconnect attempt initiated")
                        # Reset cache - status will be checked next time
                        last_known_status = None
                        last_status_time = 0
                    elif text_status is True:  # Use text analysis result if button detection failed
                        log_message("VPN appears connected based on window text analysis")
                        # Update cache
                        last_known_status = True
                        last_status_time = current_time
                        last_status_with_focus = True
                    elif text_status is False and need_to_click_connect:
                        log_message("VPN appears disconnected based on text analysis, but couldn't find a clickable Connect button")
                        # Don't update cache in this case - we're in an odd state
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
                        # Don't update cache for unclear status
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
                
                # Reset cache after reconnection
                last_known_status = None
                last_status_time = 0
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
