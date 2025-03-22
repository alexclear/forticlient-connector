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

                # Try to identify key UI elements
                result = identify_vpn_state(main_window)
                if result["identified"]:
                    log_message(f"Main window verified: VPN is {result['status']}")
                    break
                else:
                    # Fallback to old method
                    try:
                        main_window.child_window(title="Disconnect", control_type="Button").wait('exists', timeout=10)
                        log_message("Main window verified with disconnect button")
                        break
                    except:
                        main_window.child_window(title="Connect", control_type="Button").wait('exists', timeout=10)
                        log_message("Main window verified with connect button")
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
            vpn_state = identify_vpn_state(main_window)
            if vpn_state["identified"] and vpn_state["status"] == "connected":
                log_message("VPN is already connected")
                log_message("VPN connection check completed")
                return app, main_window
        except Exception as e:
            log_message(f"Error checking connection status: {e}")
            try:
                disconnect_button = main_window.child_window(title="Disconnect", control_type="Button")
                if disconnect_button.exists() and disconnect_button.is_enabled():
                    log_message("VPN is already connected (detected with standard method)")
                    return app, main_window
            except:
                pass  # Continue to connection attempt

        # Only attempt connection if not already connected
        log_message("Attempting to establish VPN connection...")
        for attempt in range(3):
            try:
                # First check if we're already connected
                vpn_state = identify_vpn_state(main_window)
                if vpn_state["identified"] and vpn_state["status"] == "connected":
                    log_message("VPN connection already active")
                    return app, main_window

                # Refresh UI elements
                main_window.restore()
                main_window.set_focus()
                main_window.wait('ready', timeout=10)

                # Try to find Connect button using multiple methods
                connect_button = find_connect_button(main_window)
                if connect_button:
                    log_message(f"Click attempt {attempt + 1}/3")
                    connect_button.click()
                    time.sleep(3)  # Wait for connection to initiate
                    break
                else:
                    log_message(f"Connect button not found for attempt {attempt + 1}")
                    raise RuntimeError("Connect button not found")

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

def find_pane_by_criteria(window, pane_id=None, depth=0, max_depth=10):
    """
    Find a specific pane in the window hierarchy by ID or recursively explore
    Returns the pane if found, otherwise None
    """
    # Base case for recursion
    if depth >= max_depth:
        return None
        
    try:
        # If we're looking for a specific pane
        if pane_id is not None:
            try:
                # Try to find by ID directly
                pane = window.child_window(best_match=pane_id)
                if pane.exists():
                    return pane
            except:
                pass
                
            # Also try to find by filtering children
            try:
                children = window.children()
                for child in children:
                    try:
                        # Check if this is the pane we're looking for
                        if hasattr(child, 'element_info') and pane_id in str(child.element_info):
                            return child
                        # Check auto_id if available
                        if hasattr(child, 'automation_id') and callable(child.automation_id) and pane_id in child.automation_id():
                            return child
                    except:
                        pass
            except:
                pass
        
        # Recursive exploration - return list of all panes
        panes = []
        try:
            children = window.children()
            for child in children:
                try:
                    # If it's a pane, add it
                    if (hasattr(child, 'element_info') and "Pane" in str(child.element_info)) or \
                       (hasattr(child, 'control_type') and callable(child.control_type) and "Pane" in child.control_type()):
                        panes.append(child)
                    
                    # Also search child's children recursively
                    child_panes = find_pane_by_criteria(child, pane_id=None, depth=depth+1, max_depth=max_depth)
                    if child_panes:
                        panes.extend(child_panes)
                except:
                    pass
        except:
            pass
            
        return panes
    except Exception as e:
        log_message(f"Error finding pane: {e}")
        return None

def explore_pane_hierarchy(window, max_depth=5):
    """
    Recursively explore the pane hierarchy
    Returns information about the pane structure
    """
    result = {
        "texts": [],
        "buttons": [],
        "panes": []
    }
    
    def _explore_element(element, depth=0):
        if depth > max_depth:
            return
            
        try:
            # Get text from this element
            try:
                if hasattr(element, 'window_text') and callable(element.window_text):
                    text = element.window_text()
                    if text and text.strip():
                        result["texts"].append(text.strip())
            except:
                pass
                
            # Check if it's a button
            try:
                if ((hasattr(element, 'control_type') and callable(element.control_type) and "button" in element.control_type().lower()) or
                    (hasattr(element, 'element_info') and "button" in str(element.element_info).lower())):
                    # It's a button - save info about it
                    button_text = element.window_text() if hasattr(element, 'window_text') and callable(element.window_text) else ""
                    if button_text:
                        result["buttons"].append({
                            "text": button_text,
                            "enabled": element.is_enabled() if hasattr(element, 'is_enabled') and callable(element.is_enabled) else False
                        })
            except:
                pass
                
            # Check if it's a pane
            try:
                if ((hasattr(element, 'control_type') and callable(element.control_type) and "pane" in element.control_type().lower()) or
                    (hasattr(element, 'element_info') and "pane" in str(element.element_info).lower())):
                    # Save info about the pane
                    pane_id = None
                    try:
                        if hasattr(element, 'automation_id') and callable(element.automation_id):
                            pane_id = element.automation_id()
                    except:
                        pass
                        
                    if not pane_id and hasattr(element, 'element_info'):
                        # Try to extract from element_info
                        info_str = str(element.element_info)
                        if 'Pane' in info_str:
                            pane_matches = re.findall(r'Pane\d+', info_str)
                            if pane_matches:
                                pane_id = pane_matches[0]
                                
                    if pane_id:
                        result["panes"].append(pane_id)
            except:
                pass
                
            # Explore children
            try:
                if hasattr(element, 'children') and callable(element.children):
                    for child in element.children():
                        _explore_element(child, depth + 1)
            except:
                pass
                
        except Exception as e:
            if DEBUG_UI_INFO:
                log_message(f"Error exploring element: {e}")
    
    # Start exploration
    _explore_element(window)
    return result

def find_content_pane(window):
    """Find the main content pane where VPN status information is likely to be"""
    # First, try to find Pane8 directly
    pane8 = None
    try:
        # Method 1: Direct approach
        pane8 = window.child_window(best_match="Pane8")
        if pane8.exists():
            log_message("Found Pane8 directly")
            return pane8
    except Exception as e:
        if DEBUG_UI_INFO:
            log_message(f"Error finding Pane8 directly: {e}")
    
    # Method 2: Try to navigate through the hierarchy
    try:
        # Get control identifiers to guide our search
        identifiers_text = ""
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            window.print_control_identifiers()
        identifiers_text = f.getvalue()
        
        # Look for the path to Pane8
        if "Pane8" in identifiers_text:
            # Typical path is Pane -> Pane3 -> Pane4 -> Pane5 -> Pane6 -> Pane8
            # Let's trace through it
            try:
                pane_collection = window.children()
                # Find Pane3
                for pane in pane_collection:
                    try:
                        if hasattr(pane, 'element_info') and "Pane3" in str(pane.element_info):
                            # Found Pane3, now look for Pane4
                            pane3 = pane
                            for subpane in pane3.children():
                                if hasattr(subpane, 'element_info') and "Pane4" in str(subpane.element_info):
                                    # Next Pane5
                                    pane4 = subpane
                                    for subsubpane in pane4.children():
                                        if hasattr(subsubpane, 'element_info') and "Pane5" in str(subsubpane.element_info):
                                            # Next Pane6
                                            pane5 = subsubpane
                                            for p6 in pane5.children():
                                                if hasattr(p6, 'element_info') and "Pane6" in str(p6.element_info):
                                                    # Finally Pane8
                                                    pane6 = p6
                                                    for p8 in pane6.children():
                                                        if hasattr(p8, 'element_info') and "Pane8" in str(p8.element_info):
                                                            pane8 = p8
                                                            log_message("Found Pane8 through hierarchy navigation")
                                                            return pane8
                    except:
                        continue
            except Exception as e:
                if DEBUG_UI_INFO:
                    log_message(f"Error navigating through pane hierarchy: {e}")
    except:
        pass
    
    # Method 3: Recursive search for Pane8
    try:
        pane8 = find_pane_by_criteria(window, pane_id="Pane8")
        if pane8:
            log_message("Found Pane8 through recursive search")
            return pane8
    except:
        pass
    
    # Method 4: As fallback, find any pane that might contain VPN info
    try:
        # Look for children with VPN-related text
        panes = find_pane_by_criteria(window)
        for pane in panes:
            try:
                text = pane.window_text() if hasattr(pane, 'window_text') and callable(pane.window_text) else ""
                if "VPN" in text or "connect" in text.lower() or "disconnect" in text.lower():
                    log_message(f"Found potential VPN content pane with text: {text[:30]}...")
                    return pane
            except:
                pass
            
            # Also check children's text
            try:
                for child in pane.children():
                    try:
                        child_text = child.window_text() if hasattr(child, 'window_text') and callable(child.window_text) else ""
                        if "VPN" in child_text or "connect" in child_text.lower() or "disconnect" in child_text.lower():
                            log_message(f"Found potential VPN content pane with child text: {child_text[:30]}...")
                            return pane
                    except:
                        pass
            except:
                pass
    except:
        pass
        
    # If all else fails, return the main window to use standard methods
    log_message("Could not find content pane, using main window")
    return window

def find_connect_button(window):
    """Use multiple methods to find the Connect button"""
    # Method 1: Standard approach
    try:
        connect_button = window.child_window(title="Connect", control_type="Button")
        if connect_button.exists():
            return connect_button
    except:
        pass
    
    # Method 2: Search by ID patterns from control identifiers
    try:
        # Try various possible identifiers based on the control hierarchy
        for identifier in ["Button", "ConnectButton", "Connect"]:
            try:
                btn = window.child_window(best_match=identifier)
                if btn.exists():
                    if btn.window_text() == "Connect":
                        return btn
            except:
                pass
    except:
        pass
    
    # Method 3: Search in window hierarchy with print_control_identifiers
    try:
        identifiers_text = ""
        # Capture the output of print_control_identifiers
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            window.print_control_identifiers()
        identifiers_text = f.getvalue()
        
        # Look for Connect button in the output
        if "Connect" in identifiers_text and "Button" in identifiers_text:
            # Extract the path from the identifiers text
            lines = identifiers_text.splitlines()
            for i, line in enumerate(lines):
                if "Button - 'Connect'" in line:
                    # Look for the child_window line that follows
                    for j in range(i, min(i+5, len(lines))):
                        if "child_window(" in lines[j] and "title=\"Connect\"" in lines[j]:
                            # Extract the specification
                            spec = lines[j].strip()
                            log_message(f"Found Connect button spec: {spec}")
                            # Try to use this spec to get the button
                            try:
                                if "control_type=\"Button\"" in spec:
                                    return window.child_window(title="Connect", control_type="Button")
                            except:
                                pass
    except Exception as e:
        log_message(f"Error in control identifier search: {e}")
    
    # Method 4: Search all descendants
    try:
        if hasattr(window, 'descendants'):
            for elem in window.descendants():
                try:
                    if elem.window_text() == "Connect" and "Button" in str(type(elem)):
                        return elem
                except:
                    pass
    except:
        pass
    
    # Method 5: Deep searching through the window hierarchy manually
    try:
        # Try to navigate through the known structure to find the button
        for child_pane in window.children():
            try:
                for subpane in child_pane.children():
                    try:
                        buttons = subpane.children(control_type="Button")
                        for button in buttons:
                            if button.window_text() == "Connect":
                                return button
                    except:
                        pass
            except:
                pass
    except Exception as e:
        log_message(f"Error in deep search: {e}")
    
    # Method 6: Try to find the content pane first, then look in it
    try:
        content_pane = find_content_pane(window)
        if content_pane and content_pane != window:
            log_message("Searching for Connect button in content pane")
            # Now search within the content pane using same methods
            try:
                connect_button = content_pane.child_window(title="Connect", control_type="Button")
                if connect_button.exists():
                    return connect_button
            except:
                pass
                
            # Try with descendants
            if hasattr(content_pane, 'descendants'):
                for elem in content_pane.descendants():
                    try:
                        if elem.window_text() == "Connect" and "Button" in str(type(elem)):
                            return elem
                    except:
                        pass
    except:
        pass
    
    return None

def find_disconnect_button(window):
    """Use multiple methods to find the Disconnect button"""
    # Method 1: Standard approach
    try:
        disconnect_button = window.child_window(title="Disconnect", control_type="Button")
        if disconnect_button.exists():
            return disconnect_button
    except:
        pass
    
    # Method 2: Search by ID patterns from control identifiers
    try:
        # Try various possible identifiers based on the control hierarchy
        for identifier in ["Button", "DisconnectButton", "Disconnect"]:
            try:
                btn = window.child_window(best_match=identifier)
                if btn.exists():
                    if btn.window_text() == "Disconnect":
                        return btn
            except:
                pass
    except:
        pass
    
    # Method 3: Search in window hierarchy with print_control_identifiers
    try:
        identifiers_text = ""
        # Capture the output of print_control_identifiers
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            window.print_control_identifiers()
        identifiers_text = f.getvalue()
        
        # Look for Disconnect button in the output
        if "Disconnect" in identifiers_text and "Button" in identifiers_text:
            # Extract the path from the identifiers text
            lines = identifiers_text.splitlines()
            for i, line in enumerate(lines):
                if "Button - 'Disconnect'" in line:
                    # Look for the child_window line that follows
                    for j in range(i, min(i+5, len(lines))):
                        if "child_window(" in lines[j] and "title=\"Disconnect\"" in lines[j]:
                            # Extract the specification
                            spec = lines[j].strip()
                            log_message(f"Found Disconnect button spec: {spec}")
                            # Try to use this spec to get the button
                            try:
                                if "control_type=\"Button\"" in spec:
                                    return window.child_window(title="Disconnect", control_type="Button")
                            except:
                                pass
    except Exception as e:
        log_message(f"Error in control identifier search: {e}")
    
    # Method 4: Search all descendants
    try:
        if hasattr(window, 'descendants'):
            for elem in window.descendants():
                try:
                    if elem.window_text() == "Disconnect" and "Button" in str(type(elem)):
                        return elem
                except:
                    pass
    except:
        pass
    
    # Method 5: Deep searching through the window hierarchy manually
    try:
        # Try to navigate through the known structure to find the button
        for child_pane in window.children():
            try:
                for subpane in child_pane.children():
                    try:
                        buttons = subpane.children(control_type="Button")
                        for button in buttons:
                            if button.window_text() == "Disconnect":
                                return button
                    except:
                        pass
            except:
                pass
    except Exception as e:
        log_message(f"Error in deep search: {e}")
    
    # Method 6: Try to find the content pane first, then look in it
    try:
        content_pane = find_content_pane(window)
        if content_pane and content_pane != window:
            log_message("Searching for Disconnect button in content pane")
            # Now search within the content pane using same methods
            try:
                disconnect_button = content_pane.child_window(title="Disconnect", control_type="Button")
                if disconnect_button.exists():
                    return disconnect_button
            except:
                pass
                
            # Try with descendants
            if hasattr(content_pane, 'descendants'):
                for elem in content_pane.descendants():
                    try:
                        if elem.window_text() == "Disconnect" and "Button" in str(type(elem)):
                            return elem
                    except:
                        pass
    except:
        pass
    
    return None

def identify_vpn_state(window):
    """
    Identify VPN state using multiple methods
    Returns a dict with keys:
    - identified: True if state was successfully identified
    - status: 'connected', 'disconnected', or 'unknown'
    - details: Additional information about the state
    """
    result = {
        "identified": False,
        "status": "unknown",
        "details": ""
    }
    
    # First, try to look in the content pane specifically
    content_pane = find_content_pane(window)
    
    # Explore the pane hierarchy to gather information
    hierarchy_info = explore_pane_hierarchy(content_pane if content_pane else window)
    
    # Log what we found for debugging
    if DEBUG_UI_INFO:
        log_message(f"Found {len(hierarchy_info['texts'])} text elements in pane hierarchy")
        log_message(f"Found {len(hierarchy_info['buttons'])} buttons in pane hierarchy")
        if hierarchy_info['texts']:
            log_message(f"First few texts: {hierarchy_info['texts'][:3]}")
        if hierarchy_info['buttons']:
            button_texts = [b['text'] for b in hierarchy_info['buttons']]
            log_message(f"Button texts: {button_texts}")
    
    # Add all the text from the pane exploration to our analysis
    full_text = " ".join(hierarchy_info['texts'])
    
    # Also check for buttons specifically
    disconnect_button_found = False
    disconnect_button_enabled = False
    connect_button_found = False
    connect_button_enabled = False
    
    for button in hierarchy_info['buttons']:
        if button['text'] == "Disconnect":
            disconnect_button_found = True
            disconnect_button_enabled = button['enabled']
        elif button['text'] == "Connect":
            connect_button_found = True
            connect_button_enabled = button['enabled']
    
    # If we didn't find buttons in hierarchy exploration, try direct methods
    if not (disconnect_button_found or connect_button_found):
        # Method 1: Use control identifiers to get a more complete view
        try:
            identifiers_text = ""
            import io
            from contextlib import redirect_stdout
            
            f = io.StringIO()
            with redirect_stdout(f):
                window.print_control_identifiers()
            identifiers_text = f.getvalue()
            
            # Add the identifiers text to our full text for analysis
            full_text += " " + identifiers_text
        except Exception as e:
            log_message(f"Error capturing control identifiers: {e}")
        
        # Method 2: Check for the presence of buttons
        disconnect_button = find_disconnect_button(window)
        connect_button = find_connect_button(window)
        
        disconnect_button_found = disconnect_button is not None
        connect_button_found = connect_button is not None
        
        if disconnect_button_found:
            try:
                disconnect_button_enabled = disconnect_button.is_enabled()
            except:
                disconnect_button_enabled = False
        
        if connect_button_found:
            try:
                connect_button_enabled = connect_button.is_enabled()
            except:
                connect_button_enabled = False
    
    # Method 3: Analyze the window text for status indicators
    connected_indicators = [
        "VPN Connected",
        "Disconnect",       # Disconnect button present
        "Duration",         # Duration field indicates active connection
        "Bytes Received", 
        "Bytes Sent",
        "IP Address",       # Connected VPNs typically show the assigned IP
        "Username"          # Connected VPNs typically show the username
    ]
    
    disconnected_indicators = [
        "Not Connected",
        "VPN Disconnected",
        "Connect"           # Connect button present
    ]
    
    found_connected = []
    for indicator in connected_indicators:
        if indicator in full_text:
            found_connected.append(indicator)
            
    found_disconnected = []
    for indicator in disconnected_indicators:
        if indicator in full_text:
            found_disconnected.append(indicator)
    
    # Add the button states to our lists if we found them directly
    if disconnect_button_found and not "Disconnect" in found_connected:
        found_connected.append("Disconnect")
    if connect_button_found and not "Connect" in found_disconnected:
        found_disconnected.append("Connect")
    
    # Analyze all the evidence to determine state
    if disconnect_button_found and disconnect_button_enabled:
        result["identified"] = True
        result["status"] = "connected"
        result["details"] = "Disconnect button found and enabled"
    elif connect_button_found and connect_button_enabled:
        result["identified"] = True
        result["status"] = "disconnected"
        result["details"] = "Connect button found and enabled"
    elif len(found_connected) >= 2:  # Require at least 2 indicators for confidence
        result["identified"] = True
        result["status"] = "connected"
        result["details"] = f"Text indicators suggest connected: {', '.join(found_connected)}"
    elif len(found_disconnected) >= 1 and not found_connected:
        result["identified"] = True
        result["status"] = "disconnected"
        result["details"] = f"Text indicators suggest disconnected: {', '.join(found_disconnected)}"
    elif "VPN Connected" in full_text:  # Special case for the most explicit indicator
        result["identified"] = True
        result["status"] = "connected"
        result["details"] = "Found explicit 'VPN Connected' text"
    elif content_pane:  # If we found a content pane but couldn't identify state, log for debugging
        result["details"] = f"Content pane found but status unclear"
        if DEBUG_UI_INFO:
            log_message(f"Content pane text: {full_text[:100]}...")
    
    return result

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
    
    # Always print control identifiers when debugging is enabled
    try:
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            window.print_control_identifiers()
        log_message(f.getvalue())
    except Exception as e:
        log_message(f"Error printing control identifiers: {e}")
    
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
            # Capture the output
            import io
            from contextlib import redirect_stdout
            
            f = io.StringIO()
            with redirect_stdout(f):
                window.print_control_identifiers()
            
            tree_text = f.getvalue()
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

            # Try to identify VPN state without setting focus
            if not need_to_set_focus:
                try:
                    # Debug window hierarchy if enabled
                    dump_window_info(main_window)
                    
                    vpn_state = identify_vpn_state(main_window)
                    
                    if vpn_state["identified"]:
                        if vpn_state["status"] == "connected":
                            log_message(f"VPN is connected: {vpn_state['details']}")
                            # Update cache
                            last_known_status = True
                            last_status_time = current_time
                            last_status_with_focus = False
                            consecutive_focus_needed = 0
                            time.sleep(check_interval)
                            continue
                        elif vpn_state["status"] == "disconnected":
                            log_message(f"VPN is disconnected: {vpn_state['details']}")
                            need_to_click_connect = True
                            need_to_set_focus = True  # Need focus to click connect
                            # Update cache
                            last_known_status = False
                            last_status_time = current_time
                            last_status_with_focus = False
                            consecutive_focus_needed = 0
                    else:
                        log_message("Could not identify VPN state without focus")
                        need_to_set_focus = True
                        consecutive_focus_needed += 1
                        log_message(f"Failed to determine status without focus {consecutive_focus_needed} time(s) in a row")
                        
                        # If we repeatedly need focus, update the global setting
                        if consecutive_focus_needed >= max_consecutive_focus and not ALWAYS_SET_FOCUS:
                            log_message("Setting ALWAYS_SET_FOCUS=True due to consistent focus requirements")
                            ALWAYS_SET_FOCUS = True
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
                
                # Check VPN state with focus
                vpn_state = identify_vpn_state(main_window)
                
                if vpn_state["identified"]:
                    if vpn_state["status"] == "connected":
                        log_message(f"VPN is connected (with focus): {vpn_state['details']}")
                        # Update cache
                        last_known_status = True
                        last_status_time = current_time
                        last_status_with_focus = True
                    elif vpn_state["status"] == "disconnected":
                        log_message(f"VPN is disconnected (with focus): {vpn_state['details']}")
                        
                        # Try to click the Connect button
                        connect_button = find_connect_button(main_window)
                        if connect_button:
                            log_message("Clicking Connect button to establish VPN connection...")
                            connect_button.click()
                            log_message("Reconnect attempt initiated")
                            # Reset cache - status will be checked next time
                            last_known_status = None
                            last_status_time = 0
                        else:
                            log_message("Could not find Connect button to click")
                            # Don't update cache in this case - we're in an odd state
                else:
                    log_message("Could not identify VPN state even with focus")
                    # Don't update cache for unclear status

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
