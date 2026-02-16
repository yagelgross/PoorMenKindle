import tkinter as tk                   # Core GUI library
from tkinter import filedialog         # For the "Open File" window

# --- External Libraries (Need to be installed) ---
import ebooklib
from ebooklib import epub              # For parsing .epub files
from bs4 import BeautifulSoup          # For cleaning HTML tags out of the EPUB

class BookWormApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("♣BookWormHole♣")
        self.geometry('600x800')
        #self.resizable(False, False)

        # The container will hold all the pages stacked on top of each other
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}

        # Initialize all pages
        for F in (StartPage, RequestPage, ReadPage):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            # Put all pages in the same location; the one on top is visible
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("StartPage")

    def show_frame(self, page_name):
        '''Show a frame for the given page name'''
        frame = self.frames[page_name]
        frame.tkraise() # This brings the specific frame to the front

class StartPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="lightblue")
        self.controller = controller

        label1 = tk.Label(self, text="Are you a Book Worm?",
                          font=("Arial", 20, "bold"), bg="cyan3")
        label1.pack(pady=(30, 10))

        label2 = tk.Label(self, text="If so, you can read your books here!",
                          font=("Arial", 15, "bold"), bg="cyan3")
        label2.pack(pady=10)

        req_btn = tk.Button(self, text="Request a Book", fg="blue", bg="cyan",
                            width=50, height=10, bd=10, relief="groove",
                            command=lambda: controller.show_frame("RequestPage"))
        req_btn.pack(pady=70)

        read_btn = tk.Button(self, text="Read a Book", fg="blue", bg="cyan",
                             width=50, height=10, bd=10, relief="groove",
                             command=lambda: controller.show_frame("ReadPage"))
        read_btn.pack(pady=30)

class RequestPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="seagreen3")
        label = tk.Label(self, text="Request Page", font=("Arial", 25), bg="seagreen3")
        label.pack(pady=100)

        back_btn = tk.Button(self, text="Back to Home",
                             command=lambda: controller.show_frame("StartPage"))
        back_btn.pack()

class ReadPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.pages = []
        self.current_page_index = 0

        # --- Font Configuration ---
        self.font_size = 13  # Default font size
        self.font_family = "Georgia"  # Default font family

        # --- Themes Configuration ---
        # List of dictionaries defining colors for different modes
        self.themes = [
            {"name": "Sepia", "bg": "#eaddcf", "fg": "black", "text_bg": "#eaddcf"},
            {"name": "Dark Mode", "bg": "#2b2b2b", "fg": "white", "text_bg": "#333333"},
            {"name": "Light Mode", "bg": "white", "fg": "black", "text_bg": "white"}
        ]
        self.current_theme_index = 0

        # Set initial background color based on the first theme
        self.configure(bg=self.themes[0]["bg"])

        # --- Header ---
        self.header = tk.Label(self, text="Reading Room", font=("Arial", 14))
        self.header.pack(pady=5)

        # --- Top Controls Frame (Theme & Font) ---
        # We create a specific frame to hold the buttons in a single row
        top_controls = tk.Frame(self, bg=self.themes[0]["bg"])
        top_controls.pack(pady=5)
        self.top_controls_frame = top_controls  # Keep reference to update bg color later

        # Decrease Font Button
        self.btn_minus = tk.Button(top_controls, text="A-", width=3,
                                   command=lambda: self.change_font_size(-2))
        self.btn_minus.pack(side="left", padx=5)

        # Toggle Theme Button
        # Note: On Mac, 'bg' might be ignored without tkmacosx or highlightbackground
        self.theme_btn = tk.Button(top_controls, text="🎨 Theme",
                                   command=self.toggle_theme, bg="gold")
        self.theme_btn.pack(side="left", padx=5)

        # Increase Font Button
        self.btn_plus = tk.Button(top_controls, text="A+", width=3,
                                  command=lambda: self.change_font_size(2))
        self.btn_plus.pack(side="left", padx=5)

        # --- Main Text Area ---
        self.text_area = tk.Text(self, wrap="word",
                                 font=(self.font_family, self.font_size),
                                 padx=40, pady=20, borderwidth=0)
        self.text_area.pack(expand=True, fill="both")

        # --- Navigation Bar (Bottom) ---
        self.nav_frame = tk.Frame(self)
        self.nav_frame.pack(fill="x", pady=10)

        self.btn_prev = tk.Button(self.nav_frame, text="◀ Prev", command=self.prev_page)
        self.btn_prev.pack(side="left", padx=50)

        self.page_label = tk.Label(self.nav_frame, text="Page 0 of 0")
        self.page_label.pack(side="left", expand=True)

        self.btn_next = tk.Button(self.nav_frame, text="Next ▶", command=self.next_page)
        self.btn_next.pack(side="right", padx=50)

        # --- File & Home Controls ---
        controls_frame = tk.Frame(self)
        controls_frame.pack(pady=5)

        tk.Button(controls_frame, text="Open EPUB", command=self.load_epub).pack(side="left", padx=5)
        tk.Button(controls_frame, text="Home", command=lambda: controller.show_frame("StartPage")).pack(side="left",
                                                                                                        padx=5)

        # Apply the initial theme colors
        self.apply_theme()

    def change_font_size(self, delta):
        """
        Adjusts the font size by 'delta' amount.
        Limits the size between 8 and 40 to prevent display issues.
        """
        new_size = self.font_size + delta

        if 8 <= new_size <= 40:
            self.font_size = new_size
            # Update the text area font immediately
            self.text_area.configure(font=(self.font_family, self.font_size))

    def toggle_theme(self):
        """
        Cycles through the available themes in self.themes list.
        """
        self.current_theme_index += 1
        if self.current_theme_index >= len(self.themes):
            self.current_theme_index = 0

        self.apply_theme()

    def apply_theme(self):
        """
        Applies the current theme colors to all relevant widgets.
        """
        theme = self.themes[self.current_theme_index]
        bg_color = theme["bg"]
        fg_color = theme["fg"]
        text_bg = theme["text_bg"]

        # 1. Update main background
        self.configure(bg=bg_color)

        # 2. Update Header
        self.header.configure(bg=bg_color, fg=fg_color)

        # 3. Update Text Area
        self.text_area.configure(bg=text_bg, fg=fg_color, insertbackground=fg_color)

        # 4. Update Navigation Bar
        self.nav_frame.configure(bg=bg_color)
        self.page_label.configure(bg=bg_color, fg=fg_color)

        # 5. Update the top controls frame background (so buttons don't look floating on wrong color)
        self.top_controls_frame.configure(bg=bg_color)

    def load_epub(self):
        """
        Opens a file dialog to select an EPUB file and parses it.
        """
        # Open file dialog
        file_path = filedialog.askopenfilename(filetypes=[("EPUB files", "*.epub")])

        if not file_path: return

        try:
            book = epub.read_epub(file_path)
            self.pages = []

            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    # Use BeautifulSoup to strip HTML tags
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text = soup.get_text().strip()
                    if text:
                        self.pages.append(text)

            self.current_page_index = 0
            self.update_page()
        except Exception as e:
            print(f"Error reading file: {e}")

    def update_page(self):
        """
        Displays the content of the current page in the text area.
        """
        if not self.pages: return

        # Enable editing temporarily to update text
        self.text_area.config(state="normal")
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert(tk.END, self.pages[self.current_page_index])

        # Disable editing to make it read-only
        self.text_area.config(state="disabled")

        self.page_label.config(text=f"Page {self.current_page_index + 1} of {len(self.pages)}")

        # Scroll to top
        self.text_area.yview_moveto(0)

    def next_page(self):
        if self.current_page_index < len(self.pages) - 1:
            self.current_page_index += 1
            self.update_page()

    def prev_page(self):
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.update_page()
if __name__ == "__main__":
    app = BookWormApp()
    app.mainloop()