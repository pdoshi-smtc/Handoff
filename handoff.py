import requests
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tkhtmlview import HTMLLabel
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, font
import re
import urllib3
import time
import json
from datetime import datetime, timedelta
import webbrowser

# Load environment variables
load_dotenv()

# Configuration
PAT = os.getenv('PAT')
VERIFY_SSL = False
BASE_URL = os.getenv('BASE_URL')
PAGE_ID = os.getenv('PAGE_ID')
SPACE_KEY = os.getenv('SPACE_KEY')
MANAGER_NAME = os.getenv('MANAGER_NAME')

# Disable SSL warnings if needed
if not VERIFY_SSL:
    urllib3.disable_warnings()

class ConfluenceClient:
    """Handle all Confluence API interactions"""
    
    def __init__(self, base_url, page_id, pat, verify_ssl=True, space_key=None):
        self.base_url = base_url
        self.page_id = page_id
        self.parent_page_id = page_id  # Store as parent page ID
        self.headers = {
            "Authorization": f"Bearer {pat}",
            "Content-Type": "application/json"
        }
        self.verify_ssl = verify_ssl
        self.current_version = None
        self.current_content = None
        self.space_key = space_key
    
    def get_current_user(self):
        """Get current authenticated user"""
        url = f"{self.base_url}/rest/api/user/current"
        try:
            response = requests.get(url, verify=self.verify_ssl, headers=self.headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching user: {e}")
        return None
    
    def search_pages_by_title(self, search_term):
        """Search for pages by title within parent page"""
        url = f"{self.base_url}/rest/api/content/{self.parent_page_id}/child/page"
        
        all_pages = []
        start = 0
        limit = 25
        
        while True:
            params = {
                "start": start,
                "limit": limit,
                "expand": "version"
            }
            
            try:
                response = requests.get(url, headers=self.headers, params=params, verify=self.verify_ssl)
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get('results', [])
                    all_pages.extend(results)
                    
                    if len(results) < limit:
                        break
                    start += limit
                else:
                    print(f"Failed to fetch child pages. Status: {response.status_code}")
                    break
            except Exception as e:
                print(f"Error searching pages: {e}")
                break
        
        # Filter pages by search term
        if search_term:
            filtered_pages = [p for p in all_pages if search_term.lower() in p['title'].lower()]
        else:
            filtered_pages = all_pages
        
        return filtered_pages
    
    def get_yesterdays_handoff(self, manager_name=None):
        """Find yesterday's handoff page"""
        yesterday = datetime.now() - timedelta(days=1)
        date_prefix = yesterday.strftime("%d-%m-%Y")
        
        # Search for pages with yesterday's date
        all_pages = self.search_pages_by_title(date_prefix)
        
        # Look for handoff pages with the pattern DD-MM-YYYY_Handoff_Manager
        handoff_pages = []
        for page in all_pages:
            # If manager name specified, look for exact match
            if manager_name:
                pattern = f"{date_prefix}_Handoff_{manager_name}"
                if page['title'] == pattern:
                    handoff_pages.append(page)
            else:
                # Look for any handoff page
                if re.match(rf"{date_prefix}_Handoff_\w+", page['title']):
                    handoff_pages.append(page)
        
        return handoff_pages
    
    def fetch_page_content(self, page_id=None):
        """Fetch page content and version"""
        if page_id is None:
            page_id = self.page_id
            
        url = f"{self.base_url}/rest/api/content/{page_id}"
        params = {"expand": "body.storage,version,body.view"}
        
        try:
            response = requests.get(url, params=params, verify=self.verify_ssl, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                if page_id == self.page_id:
                    self.current_version = data['version']['number']
                    self.current_content = data['body']['storage']['value']
                return data
            else:
                print(f"Failed to fetch page: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error fetching page: {e}")
            return None
    
    def update_page_content(self, page_id, new_content, title):
        """Update entire page content"""
        url = f"{self.base_url}/rest/api/content/{page_id}"
        
        # Get current page info
        page_data = self.fetch_page_content(page_id)
        if not page_data:
            return False, "Failed to fetch page data"
        
        update_data = {
            "version": {
                "number": page_data['version']['number'] + 1
            },
            "type": "page",
            "title": title,
            "body": {
                "storage": {
                    "value": new_content,
                    "representation": "storage"
                }
            }
        }
        
        try:
            response = requests.put(url, json=update_data, verify=self.verify_ssl, headers=self.headers)
            if response.status_code == 200:
                return True, "Page updated successfully!"
            else:
                error_msg = f"Failed to update: {response.status_code}"
                if response.status_code == 403:
                    error_msg = "No write permission"
                elif response.status_code == 409:
                    error_msg = "Version conflict - please refresh"
                return False, error_msg
        except Exception as e:
            return False, f"Error updating page: {e}"
    
    def create_daily_handoff_page(self, title=None, manager_name=""):
        """Create a new daily handoff page"""
        if not title:
            today = datetime.now().strftime("%d-%m-%Y")
            if manager_name:
                title = f"{today}_Handoff_{manager_name}"
            else:
                title = f"{today}_Handoff"
        
        space_key = self.get_space_key()
        if not space_key:
            return False, "Could not determine space key", None
        
        # Check if page already exists
        existing_pages = self.search_pages_by_title(title)
        if existing_pages:
            for page in existing_pages:
                if page['title'] == title:
                    return True, f"Page already exists", page['id']
        
        # Create new page
        create_url = f"{self.base_url}/rest/api/content"
        create_data = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": self.parent_page_id}],
            "body": {
                "storage": {
                    "value": f"""<h1>GNOC Shift Handoff</h1>

<h2>Shift Details:</h2>
<p><strong>Outgoing Manager:</strong> </p>
<p><strong>Incoming Manager:</strong> </p>
<p><strong>Date:</strong> {datetime.now().strftime("%d %B %Y")}</p>
<p><strong>Shift Time:</strong> </p>

<h2>1. Active Incidents / Ongoing Issues:</h2>
<p>&nbsp;</p>

<h2>2. Scheduled Maintenance:</h2>
<p>&nbsp;</p>

<h2>3. Alerts &amp; Monitoring Anomalies:</h2>
<p>&nbsp;</p>

<h2>4. Team Resource Status:</h2>
<p>&nbsp;</p>

<h2>5. Pending Actions / Follow-Ups:</h2>
<p>&nbsp;</p>

<h2>6. Escalations (If Any):</h2>
<p>&nbsp;</p>

<h2>7. Other Notes / Announcements:</h2>
<p>&nbsp;</p>""",
                    "representation": "storage"
                }
            }
        }
        
        try:
            response = requests.post(create_url, json=create_data, 
                                   verify=self.verify_ssl, headers=self.headers)
            
            if response.status_code == 200:
                new_page = response.json()
                page_id = new_page['id']
                return True, f"Page created successfully! (ID: {page_id})", page_id
            else:
                error_msg = f"Failed to create page: {response.status_code}"
                if response.status_code == 403:
                    error_msg = "No permission to create pages in this space"
                return False, error_msg, None
        except Exception as e:
            return False, f"Error creating page: {e}", None
    
    def delete_page(self, page_id):
        """Delete a Confluence page"""
        url = f"{self.base_url}/rest/api/content/{page_id}"
        
        try:
            response = requests.delete(url, verify=self.verify_ssl, headers=self.headers)
            
            if response.status_code == 204:
                return True, "Page deleted successfully!"
            elif response.status_code == 403:
                return False, "No permission to delete this page"
            elif response.status_code == 404:
                return False, "Page not found"
            else:
                return False, f"Failed to delete page: {response.status_code}"
        except Exception as e:
            return False, f"Error deleting page: {e}"
    
    def get_space_key(self):
        """Get space key"""
        if self.space_key:
            return self.space_key
            
        page_data = self.fetch_page_content()
        if page_data and 'space' in page_data:
            self.space_key = page_data['space']['key']
            return self.space_key
        return None
    
    def check_write_permission(self):
        """Check if user has write permission"""
        page_data = self.fetch_page_content()
        if not page_data:
            return False
        
        url = f"{self.base_url}/rest/api/content/{self.page_id}/restriction"
        try:
            response = requests.get(url, verify=self.verify_ssl, headers=self.headers)
            return response.status_code != 403
        except:
            return False


class RichTextEditor(tk.Frame):
    """Simple WYSIWYG editor with basic formatting"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="white")
        
        # Create toolbar
        self.create_toolbar()
        
        # Create text widget
        self.text = tk.Text(self, wrap=tk.WORD, font=("Arial", 11), height=15)
        self.text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Configure tags for formatting
        self.configure_tags()
        
        # Track current formatting
        self.current_tags = set()
    
    def create_toolbar(self):
        """Create formatting toolbar"""
        toolbar = tk.Frame(self, bg="#f0f0f0")
        toolbar.pack(fill="x", padx=5, pady=5)
        
        # Formatting buttons
        buttons = [
            ("B", "Bold", self.toggle_bold),
            ("I", "Italic", self.toggle_italic),
            ("U", "Underline", self.toggle_underline),
            ("•", "Bullet", self.insert_bullet),
            ("1.", "Number", self.insert_number),
            ("H1", "Heading 1", lambda: self.insert_heading(1)),
            ("H2", "Heading 2", lambda: self.insert_heading(2)),
            ("H3", "Heading 3", lambda: self.insert_heading(3)),
        ]
        
        for text, tooltip, command in buttons:
            btn = tk.Button(
                toolbar,
                text=text,
                command=command,
                width=3,
                font=("Arial", 10, "bold" if text in ["B"] else "normal"),
                relief="raised",
                bg="white"
            )
            btn.pack(side="left", padx=2)
            
            # Add tooltip
            self.create_tooltip(btn, tooltip)
        
        # Separator
        tk.Label(toolbar, text="|", bg="#f0f0f0").pack(side="left", padx=5)
        
        # Clear formatting button
        clear_btn = tk.Button(
            toolbar,
            text="Clear Format",
            command=self.clear_formatting,
            font=("Arial", 9),
            bg="white"
        )
        clear_btn.pack(side="left", padx=2)
    
    def configure_tags(self):
        """Configure text tags for formatting"""
        self.text.tag_configure("bold", font=("Arial", 11, "bold"))
        self.text.tag_configure("italic", font=("Arial", 11, "italic"))
        self.text.tag_configure("underline", underline=True)
        self.text.tag_configure("h1", font=("Arial", 16, "bold"))
        self.text.tag_configure("h2", font=("Arial", 14, "bold"))
        self.text.tag_configure("h3", font=("Arial", 12, "bold"))
        self.text.tag_configure("bullet", lmargin1=20, lmargin2=40)
        self.text.tag_configure("number", lmargin1=20, lmargin2=40)
    
    def toggle_bold(self):
        """Toggle bold formatting"""
        self.toggle_tag("bold")
    
    def toggle_italic(self):
        """Toggle italic formatting"""
        self.toggle_tag("italic")
    
    def toggle_underline(self):
        """Toggle underline formatting"""
        self.toggle_tag("underline")
    
    def toggle_tag(self, tag_name):
        """Toggle a formatting tag"""
        try:
            sel_start = self.text.index("sel.first")
            sel_end = self.text.index("sel.last")
            
            # Check if tag is already applied
            current_tags = self.text.tag_names(sel_start)
            
            if tag_name in current_tags:
                self.text.tag_remove(tag_name, sel_start, sel_end)
            else:
                self.text.tag_add(tag_name, sel_start, sel_end)
        except tk.TclError:
            # No selection, toggle for future typing
            if tag_name in self.current_tags:
                self.current_tags.remove(tag_name)
            else:
                self.current_tags.add(tag_name)
    
    def insert_bullet(self):
        """Insert bullet point"""
        self.text.insert("insert", "• ")
        self.text.tag_add("bullet", "insert linestart", "insert lineend")
    
    def insert_number(self):
        """Insert numbered list"""
        # Simple implementation - just adds "1. "
        self.text.insert("insert", "1. ")
        self.text.tag_add("number", "insert linestart", "insert lineend")
    
    def insert_heading(self, level):
        """Insert heading"""
        current_line_start = self.text.index("insert linestart")
        current_line_end = self.text.index("insert lineend")
        
        # Remove other heading tags
        for tag in ["h1", "h2", "h3"]:
            self.text.tag_remove(tag, current_line_start, current_line_end)
        
        # Apply new heading tag
        self.text.tag_add(f"h{level}", current_line_start, current_line_end)
    
    def clear_formatting(self):
        """Clear all formatting from selection"""
        try:
            sel_start = self.text.index("sel.first")
            sel_end = self.text.index("sel.last")
            
            for tag in self.text.tag_names():
                if tag != "sel":
                    self.text.tag_remove(tag, sel_start, sel_end)
        except tk.TclError:
            pass
    
    def get_html_content(self):
        """Convert formatted text to HTML"""
        html_parts = []
        
        # Get all text
        content = self.text.get("1.0", "end-1c")
        
        # Process line by line
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                html_parts.append("<p>&nbsp;</p>")
                continue
            
            line_start = f"{line_num}.0"
            line_end = f"{line_num}.end"
            
            # Check for headings
            tags = self.text.tag_names(line_start)
            
            if "h1" in tags:
                html_parts.append(f"<h1>{self.escape_html(line)}</h1>")
            elif "h2" in tags:
                html_parts.append(f"<h2>{self.escape_html(line)}</h2>")
            elif "h3" in tags:
                html_parts.append(f"<h3>{self.escape_html(line)}</h3>")
            elif "bullet" in tags:
                # Simple bullet list handling
                if not html_parts or not html_parts[-1].endswith("</ul>"):
                    html_parts.append("<ul>")
                html_parts.append(f"<li>{self.escape_html(line[2:])}</li>")
                if line_num == len(lines) or "bullet" not in self.text.tag_names(f"{line_num+1}.0"):
                    html_parts.append("</ul>")
            elif "number" in tags:
                # Simple numbered list handling
                if not html_parts or not html_parts[-1].endswith("</ol>"):
                    html_parts.append("<ol>")
                html_parts.append(f"<li>{self.escape_html(line[3:])}</li>")
                if line_num == len(lines) or "number" not in self.text.tag_names(f"{line_num+1}.0"):
                    html_parts.append("</ol>")
            else:
                # Regular paragraph with inline formatting
                formatted_line = self.process_inline_formatting(line, line_num)
                html_parts.append(f"<p>{formatted_line}</p>")
        
        return '\n'.join(html_parts)
    
    def process_inline_formatting(self, text, line_num):
        """Process inline formatting (bold, italic, underline)"""
        # This is a simplified version - in production, you'd want more sophisticated parsing
        result = self.escape_html(text)
        
        # Check each character for formatting
        formatted_parts = []
        i = 0
        
        while i < len(text):
            char_index = f"{line_num}.{i}"
            tags = self.text.tag_names(char_index)
            
            format_start = []
            format_end = []
            
            if "bold" in tags:
                format_start.append("<strong>")
                format_end.append("</strong>")
            if "italic" in tags:
                format_start.append("<em>")
                format_end.append("</em>")
            if "underline" in tags:
                format_start.append("<u>")
                format_end.append("</u>")
            
            # Find the end of this formatting
            j = i
            while j < len(text) and set(self.text.tag_names(f"{line_num}.{j}")) == set(tags):
                j += 1
            
            # Add formatted text
            formatted_text = ''.join(format_start) + self.escape_html(text[i:j]) + ''.join(reversed(format_end))
            formatted_parts.append(formatted_text)
            
            i = j
        
        return ''.join(formatted_parts) if formatted_parts else result
    
    def set_content_from_html(self, html_content):
        """Load HTML content into the editor (basic implementation)"""
        # Clear current content
        self.text.delete("1.0", tk.END)
        
        # Basic HTML to text conversion
        # Remove HTML tags for now (in production, you'd parse and apply formatting)
        text_content = re.sub('<[^<]+?>', '', html_content)
        text_content = text_content.replace('&nbsp;', ' ')
        text_content = text_content.replace('&amp;', '&')
        text_content = text_content.replace('&lt;', '<')
        text_content = text_content.replace('&gt;', '>')
        
        self.text.insert("1.0", text_content)
    
    def escape_html(self, text):
        """Escape HTML special characters"""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    def create_tooltip(self, widget, text):
        """Create tooltip for widget"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = tk.Label(tooltip, text=text, background="yellow", relief="solid", borderwidth=1)
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)


class ConfluenceEditor(tk.Tk):
    """Main GUI Application"""
    
    def __init__(self, confluence_client, manager_name):
        super().__init__()
        self.client = confluence_client
        self.manager_name = manager_name
        self.has_write_permission = False
        self.current_page_data = {}  # Store current page data for editing
        
        self.title(f"Confluence Handoff Manager - {manager_name}")
        self.geometry("1100x800")
        self.configure(bg="white")
        
        self.setup_ui()
        self.check_permissions()
    
    def setup_ui(self):
        """Setup the user interface"""
        # Top frame for status
        self.status_frame = tk.Frame(self, bg="white")
        self.status_frame.pack(fill="x", padx=10, pady=5)
        
        self.status_label = tk.Label(
            self.status_frame,
            text="Checking permissions...",
            font=("Arial", 10, "bold"),
            bg="white"
        )
        self.status_label.pack(anchor="w")
        
        # Main content area with notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Tab 1: Yesterday's Handoff
        self.handoff_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.handoff_frame, text="📋 Yesterday's Handoff")
        self.setup_handoff_tab()
        
        # Tab 2: Search & Edit
        self.search_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.search_frame, text="🔍 Search & Edit")
        self.setup_search_tab()
        
        # Tab 3: Create Page
        self.create_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.create_frame, text="➕ Create Page")
        self.setup_create_tab()
        
        # Tab 4: Delete Page
        self.delete_frame = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.delete_frame, text="🗑️ Delete Page")
        self.setup_delete_tab()
    
    def load_yesterdays_handoff(self):
        """Load and display yesterday's handoff page"""
        # Clear previous results
        for widget in self.handoff_results_frame.winfo_children():
            widget.destroy()
        
        # Get yesterday's date
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime("%d-%m-%Y")
        expected_title = f"{date_str}_Handoff_{self.manager_name}"
        
        # Get yesterday's handoff page for the manager
        handoff_pages = self.client.get_yesterdays_handoff(self.manager_name)
        
        if not handoff_pages:
            # No page found
            no_page_frame = tk.Frame(self.handoff_results_frame, bg="white")
            no_page_frame.pack(fill="both", expand=True, pady=20)
            
            tk.Label(
                no_page_frame,
                text=f"No handoff page found for {self.manager_name} yesterday",
                font=("Arial", 12),
                bg="white",
                fg="gray"
            ).pack(pady=10)
            
            tk.Label(
                no_page_frame,
                text=f"Expected page title: {expected_title}",
                font=("Arial", 10),
                bg="white",
                fg="gray"
            ).pack()
        else:
            # Found the page - directly display its content
            page = handoff_pages[0]  # Take the first (and should be only) page
            
            # Header frame with page info and buttons
            header_frame = tk.Frame(self.handoff_results_frame, bg="white", relief="ridge", bd=1)
            header_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(
                header_frame,
                text=f"Yesterday's Handoff: {page['title']}",
                font=("Arial", 12, "bold"),
                bg="white"
            ).pack(side="left", padx=10, pady=5)
            
            # Buttons on the right
            tk.Button(
                header_frame,
                text="Edit",
                command=lambda: self.load_page_for_editing(page['id'], page['title']),
                bg="#4CAF50",
                fg="white",
                font=("Arial", 10)
            ).pack(side="right", padx=5, pady=5)
            
            tk.Button(
                header_frame,
                text="Open in Browser",
                command=lambda: webbrowser.open(f"{self.client.base_url}/pages/viewpage.action?pageId={page['id']}"),
                bg="#2196F3",
                fg="white",
                font=("Arial", 10)
            ).pack(side="right", padx=5, pady=5)
            
            # Content display frame
            content_frame = tk.Frame(self.handoff_results_frame, bg="white")
            content_frame.pack(fill="both", expand=True, padx=10, pady=10)
         

            # Fetch and display the page content
            page_data = self.client.fetch_page_content(page['id'])
            
            if page_data:
                # Create scrollable HTML view
                html_view = HTMLLabel(content_frame, html=page_data['body']['view']['value'], height=60)
                html_view.pack(fill="both", expand=True)
            else:
                tk.Label(
                    content_frame,
                    text="Failed to load page content",
                    font=("Arial", 11),
                    bg="white",
                    fg="red"
                ).pack(pady=20)
 
    # For Yesterday's Handoff tab, replace the setup_handoff_tab method:
    def setup_handoff_tab(self):
        """Setup yesterday's handoff display"""
        # Title
        tk.Label(
            self.handoff_frame,
            text=f"Yesterday's Handoff Pages for {self.manager_name}",
            font=("Arial", 14, "bold"),
            bg="white"
        ).pack(pady=10)
        
        # Refresh button
        tk.Button(
            self.handoff_frame,
            text="🔄 Refresh",
            command=self.load_yesterdays_handoff,
            font=("Arial", 10),
            bg="#f0f0f0"
        ).pack(pady=5)
        
        # Create a canvas and scrollbar for scrolling
        canvas_frame = tk.Frame(self.handoff_frame)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(canvas_frame, bg="white", width=1000)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.handoff_results_frame = tk.Frame(canvas, bg="white")
        
        self.handoff_results_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.handoff_results_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Load yesterday's handoff on startup
        self.after(100, self.load_yesterdays_handoff)


    # For Search & Edit tab, replace the setup_search_tab method:
    def setup_search_tab(self):
        """Setup search and edit interface"""
        # Create main scrollable frame
        main_canvas = tk.Canvas(self.search_frame, bg="white")
        main_scrollbar = ttk.Scrollbar(self.search_frame, orient="vertical", command=main_canvas.yview)
        scrollable_frame = tk.Frame(main_canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=main_scrollbar.set)
        
        # Search section
        search_container = tk.Frame(scrollable_frame, bg="white")
        search_container.pack(fill="x", padx=20, pady=10)
        
        tk.Label(
            search_container,
            text="Search Pages:",
            font=("Arial", 12, "bold"),
            bg="white"
        ).pack(anchor="w", pady=5)
        
        # Search input
        search_input_frame = tk.Frame(search_container, bg="white")
        search_input_frame.pack(fill="x", pady=5)
        
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_input_frame,
            textvariable=self.search_var,
            font=("Arial", 11),
            width=80
        )
        self.search_entry.pack(side="left", padx=5)
        
        tk.Button(
            search_input_frame,
            text="🔍 Search",
            command=self.search_pages,
            font=("Arial", 10),
            bg="#2196F3",
            fg="white"
        ).pack(side="left", padx=5)
        
        # Search results
        self.search_results_frame = tk.Frame(scrollable_frame, bg="white")
        self.search_results_frame.pack(fill="x", padx=20, pady=10)
        
        # Separator
        ttk.Separator(scrollable_frame, orient="horizontal").pack(fill="x", padx=20, pady=10)
        
        # Edit section
        edit_container = tk.Frame(scrollable_frame, bg="white")
        edit_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        tk.Label(
            edit_container,
            text="Edit Page Content:",
            font=("Arial", 12, "bold"),
            bg="white"
        ).pack(anchor="w", pady=5)
        
        self.current_page_label = tk.Label(
            edit_container,
            text="No page selected",
            font=("Arial", 10),
            bg="white",
            fg="gray"
        )
        self.current_page_label.pack(anchor="w")
        
        # Editor mode toggle
        mode_frame = tk.Frame(edit_container, bg="white")
        mode_frame.pack(fill="x", pady=5)
        
        tk.Label(mode_frame, text="Editor Mode:", bg="white").pack(side="left", padx=5)
        
        self.editor_mode = tk.StringVar(value="wysiwyg")
        tk.Radiobutton(
            mode_frame,
            text="Visual Editor",
            variable=self.editor_mode,
            value="wysiwyg",
            command=self.toggle_editor_mode,
            bg="white"
        ).pack(side="left", padx=5)
        
        tk.Radiobutton(
            mode_frame,
            text="HTML Editor",
            variable=self.editor_mode,
            value="html",
            command=self.toggle_editor_mode,
            bg="white"
        ).pack(side="left", padx=5)
        
        # Editor container (fixed height to prevent excessive stretching)
        self.editor_container = tk.Frame(edit_container, bg="white", height=600)
        self.editor_container.pack(fill="both", expand=True, pady=10)
        self.editor_container.pack_propagate(False)  # Maintain fixed height
        
        # WYSIWYG Editor
        self.wysiwyg_editor = RichTextEditor(self.editor_container)
        self.wysiwyg_editor.pack(fill="both", expand=True)
        
        # HTML Editor (hidden initially)
        self.html_editor_frame = tk.Frame(self.editor_container, bg="white")
        self.html_editor = scrolledtext.ScrolledText(
            self.html_editor_frame,
            height=15,

            font=("Courier", 10),
            wrap=tk.WORD
        )
        self.html_editor.pack(fill="both", expand=True)
        
        # Update button
        self.update_btn = tk.Button(
            edit_container,
            text="💾 Update Page",
            command=self.update_page_content,
            font=("Arial", 11, "bold"),
            bg="#4CAF50",
            fg="white",
            state="disabled"
        )
        self.update_btn.pack(pady=10)
        
        # Pack canvas and scrollbar
        main_canvas.pack(side="left", fill="both", expand=True)
        main_scrollbar.pack(side="right", fill="y")
        
        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)




    
    def toggle_editor_mode(self):
        """Toggle between WYSIWYG and HTML editor"""
        if self.editor_mode.get() == "wysiwyg":
            # Switch to WYSIWYG
            self.html_editor_frame.pack_forget()
            self.wysiwyg_editor.pack(fill="both", expand=True)
            
            # If there's content in HTML editor, try to load it
            html_content = self.html_editor.get("1.0", tk.END).strip()
            if html_content:
                self.wysiwyg_editor.set_content_from_html(html_content)
        else:
            # Switch to HTML
            self.wysiwyg_editor.pack_forget()
            self.html_editor_frame.pack(fill="both", expand=True)
            
            # Convert WYSIWYG content to HTML
            html_content = self.wysiwyg_editor.get_html_content()
            self.html_editor.delete("1.0", tk.END)
            self.html_editor.insert("1.0", html_content)
    
    def setup_create_tab(self):
        """Setup create page interface"""
        create_container = tk.Frame(self.create_frame, bg="white")
        create_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(
            create_container,
            text="Create Daily Handoff Page",
            font=("Arial", 14, "bold"),
            bg="white"
        ).pack(pady=10)
        
        # Manager name input
        name_frame = tk.Frame(create_container, bg="white")
        name_frame.pack(pady=10)
        
        tk.Label(
            name_frame,
            text="Manager Name:",
            font=("Arial", 10),
            bg="white"
        ).pack(side="left", padx=5)
        
        self.manager_name_var = tk.StringVar(value=self.manager_name)
        tk.Entry(
            name_frame,
            textvariable=self.manager_name_var,
            font=("Arial", 11),
            width=20
        ).pack(side="left", padx=5)
        
        # Page title
        title_frame = tk.Frame(create_container, bg="white")
        title_frame.pack(pady=10)
        
        tk.Label(
            title_frame,
            text="Page Title:",
            font=("Arial", 10),
            bg="white"
        ).pack(side="left", padx=5)
        
        self.page_title_var = tk.StringVar()
        self.title_entry = tk.Entry(
            title_frame,
            textvariable=self.page_title_var,
            font=("Arial", 11),
            width=80
        )
        self.title_entry.pack(side="left", padx=5)
        
        # Auto-generate title button
        tk.Button(
            title_frame,
            text="Auto Generate",
            command=self.generate_title,
            font=("Arial", 9),
            bg="#f0f0f0"
        ).pack(side="left", padx=5)
        
        # Create button
        self.create_page_btn = tk.Button(
            create_container,
            text="📄 Create Page",
            command=self.create_page,
            font=("Arial", 12, "bold"),
            bg="#2196F3",
            fg="white",
            padx=20,
            pady=10
        )
        self.create_page_btn.pack(pady=20)
        
        # Status label
        self.create_status_label = tk.Label(
            create_container,
            text="",
            font=("Arial", 10),
            bg="white"
        )
        self.create_status_label.pack(pady=10)
    
    def setup_delete_tab(self):
        """Setup delete page interface"""
        delete_container = tk.Frame(self.delete_frame, bg="white")
        delete_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(
            delete_container,
            text="Delete Confluence Page",
            font=("Arial", 14, "bold"),
            bg="white"
        ).pack(pady=10)
        
        # Warning
        warning_frame = tk.Frame(delete_container, bg="#ffebee")
        warning_frame.pack(fill="x", pady=10)
        
        tk.Label(
            warning_frame,
            text="⚠️ Warning: Deleting a page is permanent and cannot be undone!",
            font=("Arial", 10, "bold"),
            bg="#ffebee",
            fg="#c62828"
        ).pack(padx=10, pady=10)
        
        # Search for page to delete
        tk.Label(
            delete_container,
            text="Search for page to delete:",
            font=("Arial", 11),
            bg="white"
        ).pack(pady=10)
        
        delete_search_frame = tk.Frame(delete_container, bg="white")
        delete_search_frame.pack(pady=5)
        
        self.delete_search_var = tk.StringVar()
        tk.Entry(
            delete_search_frame,
            textvariable=self.delete_search_var,
            font=("Arial", 11),
            width=80
        ).pack(side="left", padx=5)
        
        tk.Button(
            delete_search_frame,
            text="🔍 Search",
            command=self.search_pages_for_deletion,
            font=("Arial", 10),
            bg="#f0f0f0"
        ).pack(side="left", padx=5)
        
        # Results for deletion
        self.delete_results_frame = tk.Frame(delete_container, bg="white")
        self.delete_results_frame.pack(fill="both", expand=True, pady=10)
    
    def search_pages(self):
        """Search for pages"""
        search_term = self.search_var.get()
        
        # Clear previous results
        for widget in self.search_results_frame.winfo_children():
            widget.destroy()
        
        # Search pages
        pages = self.client.search_pages_by_title(search_term)
        
        if not pages:
            tk.Label(
                self.search_results_frame,
                text="No pages found",
                font=("Arial", 10),
                bg="white",
                fg="gray"
            ).pack(pady=10)
        else:
            tk.Label(
                self.search_results_frame,
                text=f"Found {len(pages)} page(s):",
                font=("Arial", 10),
                bg="white"
            ).pack(pady=5)
            
            # Display results
            for page in pages[:10]:  # Limit to 10 results
                result_frame = tk.Frame(self.search_results_frame, bg="white", relief="ridge", bd=1)
                result_frame.pack(fill="x", pady=2)
                
                tk.Label(
                    result_frame,
                    text=page['title'],
                    font=("Arial", 10),
                    bg="white"
                ).pack(side="left", padx=10, pady=5)
                
                tk.Button(
                    result_frame,
                    text="Edit",
                    command=lambda p=page: self.load_page_for_editing(p['id'], p['title']),
                    bg="#4CAF50",
                    fg="white"
                ).pack(side="right", padx=5, pady=2)
    
    def search_pages_for_deletion(self):
        """Search pages for deletion"""
        search_term = self.delete_search_var.get()
        
        # Clear previous results
        for widget in self.delete_results_frame.winfo_children():
            widget.destroy()
        
        # Search pages
        pages = self.client.search_pages_by_title(search_term)
        
        if not pages:
            tk.Label(
                self.delete_results_frame,
                text="No pages found",
                font=("Arial", 10),
                bg="white",
                fg="gray"
            ).pack(pady=10)
        else:
            # Display results
            for page in pages[:10]:  # Limit to 10 results
                result_frame = tk.Frame(self.delete_results_frame, bg="white", relief="ridge", bd=1)
                result_frame.pack(fill="x", pady=2)
                
                tk.Label(
                    result_frame,
                    text=page['title'],
                    font=("Arial", 10),
                    bg="white"
                ).pack(side="left", padx=10, pady=5)
                
                tk.Button(
                    result_frame,
                    text="🗑️ Delete",
                    command=lambda p=page: self.delete_page(p['id'], p['title']),
                    bg="#f44336",
                    fg="white"
                ).pack(side="right", padx=5, pady=2)
    
    def load_page_for_editing(self, page_id, title):
        """Load a page for editing"""
        # Fetch page content
        page_data = self.client.fetch_page_content(page_id)
        
        if page_data:
            # Store current page data
            self.current_page_data = {
                'id': page_id,
                'title': title,
                'content': page_data['body']['storage']['value']
            }
            
            # Update UI
            self.current_page_label.config(
                text=f"Editing: {title}",
                fg="black"
            )
            
            # Load content into appropriate editor
            if self.editor_mode.get() == "wysiwyg":
                self.wysiwyg_editor.set_content_from_html(self.current_page_data['content'])
            else:
                self.html_editor.delete("1.0", tk.END)
                self.html_editor.insert("1.0", self.current_page_data['content'])
            
            # Enable update button
            self.update_btn.config(state="normal")
            
            # Switch to search tab
            self.notebook.select(1)
        else:
            messagebox.showerror("Error", "Failed to load page content")
    
    def update_page_content(self):
        """Update the currently edited page"""
        if not self.current_page_data:
            messagebox.showwarning("Warning", "No page loaded for editing")
            return
        
        # Get content based on current editor mode
        if self.editor_mode.get() == "wysiwyg":
            new_content = self.wysiwyg_editor.get_html_content()
        else:
            new_content = self.html_editor.get("1.0", tk.END).strip()
        
        if not new_content:
            messagebox.showwarning("Warning", "Content cannot be empty")
            return
        
        # Confirm update
        if not messagebox.askyesno("Confirm", f"Update page '{self.current_page_data['title']}'?"):
            return
        
        # Update page
        self.update_btn.config(state="disabled", text="Updating...")
        self.update()
        
        success, message = self.client.update_page_content(
            self.current_page_data['id'],
            new_content,
            self.current_page_data['title']
        )
        
        if success:
            messagebox.showinfo("Success", message)
            self.current_page_data = {}
            self.current_page_label.config(text="No page selected", fg="gray")
            self.wysiwyg_editor.text.delete("1.0", tk.END)
            self.html_editor.delete("1.0", tk.END)
        else:
            messagebox.showerror("Error", message)
        
        self.update_btn.config(state="normal", text="💾 Update Page")
    
    def generate_title(self):
        """Generate automatic title"""
        manager_name = self.manager_name_var.get().strip()
        today = datetime.now().strftime("%d-%m-%Y")
        
        if manager_name:
            title = f"{today}_Handoff_{manager_name}"
        else:
            title = f"{today}_Handoff"
        
        self.page_title_var.set(title)
    
    def create_page(self):
        """Create a new page"""
        title = self.page_title_var.get().strip()
        manager_name = self.manager_name_var.get().strip()
        
        if not title:
            # Generate title if not provided
            self.generate_title()
            title = self.page_title_var.get()
        
        # Confirm creation
        if not messagebox.askyesno("Confirm", f"Create page: '{title}'?"):
            return
        
        # Create page
        self.create_page_btn.config(state="disabled", text="Creating...")
        self.create_status_label.config(text="Creating page...", fg="blue")
        self.update()
        
        success, message, page_id = self.client.create_daily_handoff_page(title, manager_name)
        
        if success:
            self.create_status_label.config(
                text=f"✅ {message}",
                fg="green"
            )
            
            # Option to view page
            if messagebox.askyesno("Success", f"{message}\n\nOpen page in browser?"):
                page_url = f"{self.client.base_url}/pages/viewpage.action?pageId={page_id}"
                webbrowser.open(page_url)
            
            # Clear form
            self.page_title_var.set("")
        else:
            self.create_status_label.config(
                text=f"❌ {message}",
                fg="red"
            )
        
        self.create_page_btn.config(state="normal", text="📄 Create Page")
    
    def delete_page(self, page_id, title):
        """Delete a page"""
        # Double confirmation for safety
        if not messagebox.askyesno("Confirm Delete", 
                                  f"Are you sure you want to delete:\n\n'{title}'?\n\nThis action cannot be undone!"):
            return
        
        if not messagebox.askyesno("Final Confirmation", 
                                  "This is your last chance!\n\nReally delete this page?"):
            return
        
        # Delete page
        success, message = self.client.delete_page(page_id)
        
        if success:
            messagebox.showinfo("Success", message)
            # Refresh the delete search results
            self.search_pages_for_deletion()
        else:
            messagebox.showerror("Error", message)
    
    def view_page_content(self, page):
        """View page content in a popup"""
        page_data = self.client.fetch_page_content(page['id'])
        
        if page_data:
            # Create popup window
            popup = tk.Toplevel(self)
            popup.title(f"View: {page['title']}")
            popup.geometry("800x600")
            
            # Display content
            html_view = HTMLLabel(popup, html=page_data['body']['view']['value'])
            html_view.pack(fill="both", expand=True, padx=10, pady=10)
            
            # Buttons
            btn_frame = tk.Frame(popup)
            btn_frame.pack(fill="x", pady=5)
            
            tk.Button(
                btn_frame,
                text="Edit",
                command=lambda: [popup.destroy(), self.load_page_for_editing(page['id'], page['title'])],
                bg="#4CAF50",
                fg="white"
            ).pack(side="left", padx=5)
            
            tk.Button(
                btn_frame,
                text="Open in Browser",
                command=lambda: webbrowser.open(f"{self.client.base_url}/pages/viewpage.action?pageId={page['id']}"),
                bg="#2196F3",
                fg="white"
            ).pack(side="left", padx=5)
            
            tk.Button(
                btn_frame,
                text="Close",
                command=popup.destroy
            ).pack(side="right", padx=5)
    
    def check_permissions(self):
        """Check and display permissions"""
        self.has_write_permission = self.client.check_write_permission()
        
        if self.has_write_permission:
            self.status_label.config(
                text=f"✅ Your have Read Write Permissions",
                fg="green"
            )
        else:
            self.status_label.config(
                text="❌ You dont have Write Permissiona",
                fg="red"
            )


def wait_for_internet(timeout=300, check_interval=5):
    """Wait for internet connection"""
    print("🌐 Checking internet connection...")
    start = time.time()
    
    while True:
        try:
            requests.get("https://www.google.com", timeout=5)
            print("✅ Internet connection available.")
            return True
        except requests.RequestException:
            if time.time() - start > timeout:
                print("❌ Timeout: Internet still not available.")
                return False
            print("🌐 Waiting for internet connection...")
            time.sleep(check_interval)


if __name__ == "__main__":
    if wait_for_internet():
        # Initialize Confluence client
        client = ConfluenceClient(BASE_URL, PAGE_ID, PAT, VERIFY_SSL, SPACE_KEY)
        
        # Check current user
        user = client.get_current_user()
        if user:
            print(f"✅ Authenticated as: {user.get('displayName', 'Unknown')}")
        
        # Launch GUI with manager name
        app = ConfluenceEditor(client, MANAGER_NAME)
        app.mainloop()
    else:
        print("❌ Could not connect to the internet after waiting.")