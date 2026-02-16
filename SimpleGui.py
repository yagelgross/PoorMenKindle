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
        super().__init__(parent, bg="#fdf6e3")
        self.controller = controller
        self.pages = []
        self.current_page_index = 0

        # Title/Header
        self.header = tk.Label(self, text="Reading Room", font=("Arial", 14), bg="#fdf6e3")
        self.header.pack(pady=5)

        self.themes = [
            {"name": "Sepia", "bg": "#e3dccb", "fg": "black", "text_bg": "#fdf6e3"},
            {"name": "Dark Mode", "bg": "#2b2b2b", "fg": "white", "text_bg": "#333333"},
            {"name": "Light Mode", "bg": "white", "fg": "black", "text_bg": "white"}
        ]
        self.current_theme_index = 0
        self.configure(bg=self.themes[0]["bg"])

        self.header = tk.Label(self, text="Reading Room", font=("Arial", 14))
        self.header.pack(pady=5)

        self.theme_btn = tk.Button(self, text="Theme", command=self.toggle_theme, bg="gold")
        self.theme_btn.pack(pady=2)

        # Text Area
        self.text_area = tk.Text(self, wrap="word", font=("Georgia", 13),
                                 padx=40, pady=20, borderwidth=0)
        self.text_area.pack(expand=True, fill="both")

        # Navigation Frame
        self.nav_frame = tk.Frame(self)
        self.nav_frame.pack(fill="x", pady=10)

        self.btn_prev = tk.Button(self.nav_frame, text="◀ Prev", command=self.prev_page)
        self.btn_prev.pack(side="left", padx=50)

        self.page_label = tk.Label(self.nav_frame, text="Page 0 of 0")
        self.page_label.pack(side="left", expand=True)

        self.btn_next = tk.Button(self.nav_frame, text="Next ▶", command=self.next_page)
        self.btn_next.pack(side="right", padx=50)

        # File Controls Frame (למטה)
        controls_frame = tk.Frame(self)
        controls_frame.pack(pady=5)

        tk.Button(controls_frame, text="Open EPUB", command=self.load_epub).pack(side="left", padx=5)
        tk.Button(controls_frame, text="Home", command=lambda: controller.show_frame("StartPage")).pack(side="left",
                                                                                                        padx=5)

        # החלת הצבעים הראשוניים
        self.apply_theme()

    def toggle_theme(self):
        """פונקציה שעוברת לערכת הנושא הבאה ברשימה"""
        self.current_theme_index += 1
        if self.current_theme_index >= len(self.themes):
            self.current_theme_index = 0

        self.apply_theme()

    def apply_theme(self):
        """פונקציה שצובעת את כל הרכיבים לפי הערכה הנוכחית"""
        theme = self.themes[self.current_theme_index]
        bg_color = theme["bg"]
        fg_color = theme["fg"]
        text_bg = theme["text_bg"]

        # 1. צביעת הרקע של העמוד הראשי
        self.configure(bg=bg_color)

        # 2. צביעת הכותרת
        self.header.configure(bg=bg_color, fg=fg_color)

        # 3. צביעת איזור הטקסט
        self.text_area.configure(bg=text_bg, fg=fg_color, insertbackground=fg_color)

        # 4. צביעת איזור הניווט והתווית
        self.nav_frame.configure(bg=bg_color)
        self.page_label.configure(bg=bg_color, fg=fg_color)
    def load_epub(self):
        file_path = filedialog.askopenfilename(filetypes=[("EPUB files", "*.epub")])
        #file_path = "booksForServer/Eragon (Christopher Paolini).epub"
        if not file_path: return

        book = epub.read_epub(file_path)
        self.pages = []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text = soup.get_text().strip()
                if text:
                    # Optional: Split very long chapters into smaller chunks
                    # Here we just treat each chapter as a page for simplicity
                    self.pages.append(text)

        self.current_page_index = 0
        self.update_page()

    def update_page(self):
        if not self.pages: return

        self.text_area.config(state="normal")  # Enable editing to change text
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert(tk.END, self.pages[self.current_page_index])
        self.text_area.config(state="disabled")  # Disable again so it's read-only

        self.page_label.config(text=f"Page {self.current_page_index + 1} of {len(self.pages)}")
        self.text_area.yview_moveto(0)  # Reset scroll to top of new page

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