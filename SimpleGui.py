from tkinter import filedialog

# --- External Libraries ---
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from PIL import Image, ImageTk

import util


import tkinter as tk
import threading
from network_manager import NetworkManager

class BookWormApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("♣BookWormHole♣")
        self.geometry('600x800')

        # Persistent network manager (shared across pages)
        self.net_manager = NetworkManager(host='127.0.0.1', port=12347)

        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (LoginPage, StartPage, RequestPage, ReadPage):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginPage")

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()


class LoginPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#eaddcf")
        self.controller = controller

        title = tk.Label(self, text="Login to BookWormHole", font=("Arial", 20, "bold"), bg="#eaddcf")
        title.pack(pady=(60, 20))

        # Server IP field (needed when connecting from a VM or different machine)
        ip_label = tk.Label(self, text="Server IP:", font=("Arial", 12), bg="#eaddcf")
        ip_label.pack(pady=(10, 0))
        self.ip_entry = tk.Entry(self, font=("Arial", 12), width=25)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(pady=5)

        user_label = tk.Label(self, text="Username:", font=("Arial", 12), bg="#eaddcf")
        user_label.pack(pady=(10, 0))
        self.username_entry = tk.Entry(self, font=("Arial", 12), width=25)
        self.username_entry.pack(pady=5)

        pass_label = tk.Label(self, text="Password:", font=("Arial", 12), bg="#eaddcf")
        pass_label.pack(pady=(10, 0))
        self.password_entry = tk.Entry(self, font=("Arial", 12), width=25, show="*")
        self.password_entry.pack(pady=5)

        self.error_label = tk.Label(self, text="", fg="red", bg="#eaddcf", font=("Arial", 10))
        self.error_label.pack(pady=5)

        login_btn = tk.Button(self, text="Login", font=("Arial", 12, "bold"), bg="cyan", width=15,
                              command=self.check_login)
        login_btn.pack(pady=20)

    def check_login(self):
        user = self.username_entry.get()
        password = self.password_entry.get()
        server_ip = self.ip_entry.get().strip()

        if not user or not password:
            self.error_label.config(text="Please fill in all fields!")
            return

        if not server_ip:
            self.error_label.config(text="Please enter the server IP address!")
            return

        net = self.controller.net_manager
        # Update the host in case the user changed it (e.g. connecting from a VM)
        net.host = server_ip

        if not net.sock or net.sock.fileno() == -1:
            if not net.connect():
                self.error_label.config(text="Server is offline. Cannot connect.")
                return

        response = net.login(user, password)

        if response == "SUCCESS":
            self.controller.show_frame("StartPage")
        elif response == "FAIL":
            self.error_label.config(text="Invalid username or password!")
        else:
            self.error_label.config(text="Server error occurred.")


def _create_card_button(parent, title_text, desc_text,
                        bg_color, hover_color, command):
    """Build a rounded-look card button with a title and description label."""
    # Outer frame acts as the "card"
    card = tk.Frame(parent, bg=bg_color, padx=22, pady=14,
                    cursor="hand2", relief="flat", bd=0)

    # Title label
    title_lbl = tk.Label(card, text=title_text,
                         font=("Arial", 16, "bold"), fg="white",
                         bg=bg_color, anchor="w")
    title_lbl.pack(anchor="w")

    # Description label
    desc_lbl = tk.Label(card, text=desc_text,
                        font=("Arial", 10), fg="#e0f2f1",
                        bg=bg_color, anchor="w", justify="left")
    desc_lbl.pack(anchor="w", pady=(4, 0))

    # Force a minimum width to match the JavaFX 380px feel
    card.configure(width=380, height=90)
    card.pack_propagate(False)

    # Hover effects — change background of card + child labels
    def on_enter(_):
        for widget in (card, title_lbl, desc_lbl):
            widget.configure(bg=hover_color)

    def on_leave(_):
        for widget in (card, title_lbl, desc_lbl):
            widget.configure(bg=bg_color)

    for widget in (card, title_lbl, desc_lbl):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        widget.bind("<Button-1>", lambda e: command())

    return card


class StartPage(tk.Frame):
    # Color palette matching the JavaFX gradient theme
    BG_COLOR = "#b2ebf2"       # Mid-tone teal used as the flat fallback
    ACCENT_DARK = "#00695c"    # Dark teal for title text
    ACCENT_MID = "#004d40"     # Darker shade for subtitle
    DIVIDER_COLOR = "#80cbc4"  # Soft teal for decorative elements
    BTN1_BG = "#00897b"        # Request button background
    BTN1_HOVER = "#00695c"     # Request button hover
    BTN2_BG = "#0097a7"        # Read button background
    BTN2_HOVER = "#00838f"     # Read button hover

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # --- Gradient background using a Canvas ---
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._draw_gradient)

        # --- Content frame (transparent, sits on top of canvas) ---
        content = tk.Frame(self, bg="")
        content.place(relx=0.5, rely=0.5, anchor="center")
        # Make the content frame background invisible by matching gradient mid-tone
        content.configure(bg=self.BG_COLOR)

        # --- Header section ---
        header = tk.Frame(content, bg=self.BG_COLOR)
        header.pack(pady=(20, 10))

        tk.Label(header, text="📚", font=("Arial", 44),
                 bg=self.BG_COLOR).pack()

        tk.Label(header, text="Welcome, Book Worm!",
                 font=("Arial", 26, "bold"), fg=self.ACCENT_DARK,
                 bg=self.BG_COLOR).pack(pady=(8, 2))

        tk.Label(header, text="Dive into your next adventure",
                 font=("Arial", 14, "italic"), fg=self.ACCENT_MID,
                 bg=self.BG_COLOR).pack()

        tk.Label(header, text="─────────  ♣  ─────────",
                 font=("Arial", 13), fg=self.DIVIDER_COLOR,
                 bg=self.BG_COLOR).pack(pady=(10, 0))

        # --- Buttons section ---
        btn_frame = tk.Frame(content, bg=self.BG_COLOR)
        btn_frame.pack(pady=(25, 10))

        _create_card_button(
            btn_frame,
            title_text="📖  Request a Book",
            desc_text="Browse the library and request a book\nfrom the server to start reading",
            bg_color=self.BTN1_BG,
            hover_color=self.BTN1_HOVER,
            command=lambda: controller.show_frame("RequestPage")
        ).pack(pady=(0, 20))

        _create_card_button(
            btn_frame,
            title_text="📖  Read a Book",
            desc_text="Open an EPUB file from your\ncomputer and read it offline",
            bg_color=self.BTN2_BG,
            hover_color=self.BTN2_HOVER,
            command=lambda: controller.show_frame("ReadPage")
        ).pack()

        # --- Footer ---
        tk.Label(content, text="♣ BookWormHole ♣",
                 font=("Arial", 11, "bold"), fg=self.DIVIDER_COLOR,
                 bg=self.BG_COLOR).pack(pady=(30, 15))

    # ---- Helpers ----

    def _draw_gradient(self, event=None):
        """Draw a vertical gradient on the background canvas (top-to-bottom teal)."""
        self.canvas.delete("gradient")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        # Three-stop gradient: #e0f7fa  →  #b2ebf2  →  #80deea
        colors = [
            (0xe0, 0xf7, 0xfa),  # light top
            (0xb2, 0xeb, 0xf2),  # mid
            (0x80, 0xde, 0xea),  # darker bottom
        ]

        steps = h
        for i in range(steps):
            t = i / max(steps - 1, 1)
            # Interpolate across the three stops
            if t < 0.5:
                local_t = t / 0.5
                r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * local_t)
                g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * local_t)
                b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * local_t)
            else:
                local_t = (t - 0.5) / 0.5
                r = int(colors[1][0] + (colors[2][0] - colors[1][0]) * local_t)
                g = int(colors[1][1] + (colors[2][1] - colors[1][1]) * local_t)
                b = int(colors[1][2] + (colors[2][2] - colors[1][2]) * local_t)

            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(0, i, w, i, fill=hex_color, tags="gradient")


class RequestPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="seagreen3")
        self.controller = controller

        label = tk.Label(self, text="Request Page", font=("Arial", 25), bg="seagreen3")
        label.pack(pady=30)

        # Book data: (title, image_path)
        self.books = [
            ("Eragon", "ImagesForBooks/Eragon.jpg"),
            ("Eldest", "ImagesForBooks/Eldest.png"),
            ("Brisingr", "ImagesForBooks/Brisingr.png"),
            ("Inheritance", "ImagesForBooks/Inheritance.jpg"),
        ]

        self.photos = []
        gallery_frame = tk.Frame(self, bg="seagreen3")
        gallery_frame.pack(pady=20)

        for i, (title, img_path) in enumerate(self.books):
            try:
                img = Image.open(img_path).resize((100, 130))
                photo = ImageTk.PhotoImage(img)
                self.photos.append(photo)

                btn = tk.Button(gallery_frame, image=photo, bd=0, cursor="hand2",
                                command=lambda t=title: self.request_book(t))
                btn.grid(row=0, column=i, padx=15, pady=15)

                lbl = tk.Label(gallery_frame, text=title, bg="seagreen3",
                               font=("Arial", 10, "bold"))
                lbl.grid(row=1, column=i)
            except Exception as e:
                print(f"Error loading image for {title}: {e}")

        back_btn = tk.Button(self, text="Back to Home", font=("Arial", 12),
                             command=lambda: controller.show_frame("StartPage"))
        back_btn.pack(pady=30)

    def request_book(self, book_title):
        """Called when user clicks a book cover."""
        net_manager = self.controller.net_manager  # stored on the app controller

        def do_request():
            success = net_manager.request_book(book_title)
            if success:
                # Switch to ReadPage and start displaying
                read_page = self.controller.frames["ReadPage"]
                read_page.start_reading(net_manager)
                self.controller.show_frame("ReadPage")
            else:
                import tkinter.messagebox
                tkinter.messagebox.showerror("Error", f"Could not load '{book_title}'")

        # Run in a thread so UI doesn't freeze
        threading.Thread(target=do_request, daemon=True).start()

class ReadPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.net_manager = None
        self.current_page_index = 0
        self.total_chapters = 0
        self.pages = []  # For local epub reading
        self.reading_mode = None  # "server" or "local"
        self.is_hebrew = False  # Whether the current book is in Hebrew (RTL)

        # --- Font Configuration ---
        self.font_size = 13
        self.font_family = "Georgia"

        # List of available fonts for the menu
        self.available_fonts = ["Charter", "Hoefler Text", "Palatino", "Baskerville",
                                "Georgia", "Times New Roman", "Avenir Next", "Helvetica Neue",
                                "Verdana", "Arial", "Courier New", "New Peninim MT", "Comic sans", "Raanana", "Arial Hebrew"]

        # --- Themes Configuration ---
        self.themes = [
            {"name": "Sepia", "bg": "#eaddcf", "fg": "black", "text_bg": "#eaddcf"},
            {"name": "Dark Mode", "bg": "#2b2b2b", "fg": "white", "text_bg": "#333333"},
            {"name": "Light Mode", "bg": "white", "fg": "black", "text_bg": "white"}
        ]
        self.current_theme_index = 0

        self.configure(bg=self.themes[0]["bg"])

        # --- Header ---
        self.header = tk.Label(self, text="Reading Room", font=("Arial", 14))
        self.header.pack(pady=5)

        # --- Top Controls Frame ---
        top_controls = tk.Frame(self, bg=self.themes[0]["bg"])
        top_controls.pack(pady=5)
        self.top_controls_frame = top_controls

        # 1. Decrease Font Button
        self.btn_minus = tk.Button(top_controls, text="A-", width=3,
                                   command=lambda: self.change_font_size(-2))
        self.btn_minus.pack(side="left", padx=5)

        # 2. Theme Button
        self.theme_btn = tk.Button(top_controls, text="🎨 Theme",
                                   command=self.toggle_theme, bg="gold")
        self.theme_btn.pack(side="left", padx=5)

        # 3. Font Family Button
        self.btn_font = tk.Button(top_controls, text="🔤 Font", bg="lightblue")
        self.btn_font.pack(side="left", padx=5)

        # Create the popup menu for fonts
        self.font_menu = tk.Menu(self, tearoff=0)
        for f in self.available_fonts:
            self.font_menu.add_command(label=f, command=lambda f=f: self.change_font_family(f))

        # Bind the left mouse click to show the menu
        self.btn_font.bind("<Button-1>", self.do_popup)

        # 4. Increase Font Button
        self.btn_plus = tk.Button(top_controls, text="A+", width=3,
                                  command=lambda: self.change_font_size(2))
        self.btn_plus.pack(side="left", padx=5)

        # --- Main Text Area ---
        self.text_area = tk.Text(self, wrap="word",
                                 font=(self.font_family, self.font_size),
                                 padx=40, pady=20, borderwidth=0)
        self.text_area.pack(expand=True, fill="both")

        # --- Navigation Bar ---
        self.nav_frame = tk.Frame(self)
        self.nav_frame.pack(fill="x", pady=10)

        self.btn_prev = tk.Button(self.nav_frame, text="◀ Prev", command=self.prev_page)
        self.btn_prev.pack(side="left", padx=50)

        self.page_label = tk.Label(self.nav_frame, text="Page 0 of 0")
        self.page_label.pack(side="left", expand=True)

        self.btn_next = tk.Button(self.nav_frame, text="Next ▶", command=self.next_page)
        self.btn_next.pack(side="right", padx=50)

        # --- Footer Controls ---
        controls_frame = tk.Frame(self)
        controls_frame.pack(pady=5)
        tk.Button(controls_frame, text="Home",
                  command=lambda: controller.show_frame("StartPage")).pack(side="left", padx=5)
        tk.Button(controls_frame, text="📂 Load EPUB",
                  command=self.load_epub).pack(side="left", padx=5)

        self.loading_label = tk.Label(self, text="", font=("Arial", 10, "italic"))
        self.loading_label.pack(pady=2)

        self.apply_theme()

    def start_reading(self, net_manager):
        """Called when a book is successfully requested from the server."""
        self.reading_mode = "server"
        self.net_manager = net_manager
        self.current_page_index = 0
        self.total_chapters = net_manager.total_chapters
        self.is_hebrew = self._contains_hebrew(net_manager.book_title)

        # Set callback: when a chapter arrives, refresh if needed
        net_manager.on_chapter_ready = self._on_chapter_ready

        # Wait briefly for first chapter, then display
        self.after(100, self._try_display_current)

    def _on_chapter_ready(self, chapter_index: int):
        """Called from the prefetch thread when a new chapter is buffered."""
        # Use `after` to safely update the UI from the main thread
        if chapter_index == self.current_page_index:
            self.after(0, self._try_display_current)

    def _try_display_current(self):
        """Attempt to display the current chapter from the buffer."""
        if not self.net_manager:
            return

        text = self.net_manager.get_chapter(self.current_page_index)
        if text is not None:
            self.loading_label.config(text="")
            self._display_chapter(text)
        else:
            self.loading_label.config(text="Loading chapter...")
            # Retry in 200ms
            self.after(200, self._try_display_current)

    def _display_chapter(self, full_text: str):
        """Render a chapter in the text area (same logic as your update_page)."""
        self.text_area.config(state="normal")
        self.text_area.delete('1.0', tk.END)

        if '\n' in full_text:
            title_text, body_text = full_text.split('\n', 1)
        else:
            title_text = full_text
            body_text = ""

        self.text_area.insert(tk.END, title_text + "\n")
        self.update_title_style()
        self.text_area.tag_add("title_style", "1.0", "1.end")
        self.text_area.insert(tk.END, body_text)
        self._apply_rtl_direction()

        self.text_area.config(state="disabled")
        self.page_label.config(text=f"Chapter {self.current_page_index + 1} of {self.total_chapters}")
        self.text_area.yview_moveto(0)

        # Show buffer status
        buffered = self.net_manager.next_server_index - self.current_page_index
        self.loading_label.config(text=f"📦 {buffered} chapter(s) buffered ahead")

    def next_page(self):
        """Advance to the next page/chapter (works for both server and local modes)."""
        if self.reading_mode == "server":
            if self.current_page_index < self.total_chapters - 1:
                self.current_page_index += 1
                self.net_manager.notify_user_advanced(self.current_page_index)
                self._try_display_current()
        elif self.reading_mode == "local":
            if self.current_page_index < len(self.pages) - 1:
                self.current_page_index += 1
                self.update_page()

    def prev_page(self):
        #Go back to the previous page/chapter (works for both server and local modes).
        if self.current_page_index > 0:
            self.current_page_index -= 1
            if self.reading_mode == "server":
                self._try_display_current()
            elif self.reading_mode == "local":
                self.update_page()

    # --- HELPER: Update the Title Tag Style ---
    def update_title_style(self):
        """
        Configures the 'title_style' tag.
        Updates whenever the font size, family, or theme changes.
        """
        current_fg = self.themes[self.current_theme_index]["fg"]

        self.text_area.tag_configure("title_style",
                                     font=(self.font_family, self.font_size + 3, "bold"),  # Size + 3, Bold
                                     justify='right' if self.is_hebrew else 'center',  # RTL or center
                                     underline=True,  # Underscore
                                     foreground=current_fg  # Match theme color
                                     )

    # --- Functions ---
    def do_popup(self, event):
        try:
            self.font_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.font_menu.grab_release()

    def change_font_family(self, new_family):
        self.font_family = new_family
        self.text_area.configure(font=(self.font_family, self.font_size))
        # Update title style to match the new font family
        self.update_title_style()

    def change_font_size(self, delta):
        new_size = self.font_size + delta
        if 8 <= new_size <= 40:
            self.font_size = new_size
            self.text_area.configure(font=(self.font_family, self.font_size))
            # Update the title style to match the new size
            self.update_title_style()

    def toggle_theme(self):
        self.current_theme_index += 1
        if self.current_theme_index >= len(self.themes):
            self.current_theme_index = 0
        self.apply_theme()

    @staticmethod
    def _contains_hebrew(text: str) -> bool:
        """Check if a string contains Hebrew characters (Unicode block 0x0590-0x05FF)."""
        return any('\u0590' <= ch <= '\u05FF' for ch in text)

    def _apply_rtl_direction(self):
        """Configure the text area for RTL (Hebrew) or LTR display."""
        if self.is_hebrew:
            self.text_area.tag_configure("rtl", justify="right")
            self.text_area.tag_add("rtl", "1.0", tk.END)
        else:
            self.text_area.tag_remove("rtl", "1.0", tk.END)

    def apply_theme(self):
        theme = self.themes[self.current_theme_index]
        bg_color = theme["bg"]
        fg_color = theme["fg"]
        text_bg = theme["text_bg"]

        self.configure(bg=bg_color)
        self.header.configure(bg=bg_color, fg=fg_color)
        self.text_area.configure(bg=text_bg, fg=fg_color, insertbackground=fg_color)
        self.nav_frame.configure(bg=bg_color)
        self.page_label.configure(bg=bg_color, fg=fg_color)
        self.top_controls_frame.configure(bg=bg_color)

        # Update title color
        self.update_title_style()

    def load_epub(self):
        """Open a file dialog to load a local .epub file and switch to local reading mode."""
        file_path = filedialog.askopenfilename(filetypes=[("EPUB files", "*.epub")])
        if not file_path: return

        try:
            book = epub.read_epub(file_path)
            self.pages = []
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text = soup.get_text().strip()
                    if text:
                        self.pages.append(text)
            self.reading_mode = "local"
            self.current_page_index = 0
            self.total_chapters = len(self.pages)
            # Detect Hebrew from the file name
            import os
            self.is_hebrew = self._contains_hebrew(os.path.basename(file_path))
            self.update_page()
        except Exception as e:
            import tkinter
            tkinter.messagebox.showerror("Error", f"Failed to load EPUB file: {e}")

    def update_page(self):
        if not self.pages: return

        self.text_area.config(state="normal")
        self.text_area.delete('1.0', tk.END)

        full_text = self.pages[self.current_page_index]

        # Split text into Title (first line) and Body (rest)
        if '\n' in full_text:
            title_text, body_text = full_text.split('\n', 1)
        else:
            title_text = full_text
            body_text = ""

        # 1. Insert Title
        self.text_area.insert(tk.END, title_text + "\n")

        # 2. Apply the 'title_style' tag to the first line
        self.update_title_style()
        self.text_area.tag_add("title_style", "1.0", "1.end")

        # 3. Insert the rest of the body
        self.text_area.insert(tk.END, body_text)
        self._apply_rtl_direction()

        self.text_area.config(state="disabled")
        self.page_label.config(text=f"Page {self.current_page_index + 1} of {len(self.pages)}")
        self.text_area.yview_moveto(0)



if __name__ == "__main__":
    app = BookWormApp()
    app.mainloop()