from tkinter import filedialog

# --- External Libraries ---
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from PIL import Image, ImageTk
import io
import base64
import tkinter as tk
import threading
from network_manager import NetworkManager
import dns.message
import dns.query


class BookWormApp(tk.Tk):
    """A class to represent the main application window for the client."""
    def __init__(self):
        super().__init__() # initialize the tkinter window
        self.title("♣BookWormHole♣") # the name of the app
        self.geometry('700x800') # the size of the opened window at first

        # Persistent network manager (shared across pages)
        self.net_manager = NetworkManager(host='127.0.0.1', port=12347)

        container = tk.Frame(self) # initialize the container frame
        container.pack(side="top", fill="both", expand=True) # place the container frame at the top of the window
        container.grid_rowconfigure(0, weight=1) # make the container frame take up all available space vertically
        container.grid_columnconfigure(0, weight=1) # make the container frame take up all available space horizontally

        self.frames = {} # dictionary to hold the frames
        for F in (LoginPage, StartPage, RequestPage, ReadPage): # create a frame for each page
            page_name = F.__name__ # get the name of the page class (e.g., "LoginPage")
            frame = F(parent=container, controller=self) # create an instance of the page class
            self.frames[page_name] = frame # add the frame to the dictionary
            frame.grid(row=0, column=0, sticky="nsew") # place the frame in the container

        self.show_frame("LoginPage") # show the first frame (the login page)

    def show_frame(self, page_name):
        """Show a frame for the given page name."""
        frame = self.frames[page_name] # retrieve the frame based on the page name
        frame.tkraise() # raise the frame to the top of the stacking order


class LoginPage(tk.Frame):
    """A class representing the Login page for the application."""
    def __init__(self, parent, controller):
        """Initialize the LoginPage. The required fields are Server IP, Protocol (TCP/RUDP), Username, and Password."""
        super().__init__(parent, bg="#eaddcf")
        self.controller = controller # reference to the main application controller

        title = tk.Label(self, text="Login to BookWormHole", font=("Arial", 20, "bold"), bg="#eaddcf") # the header of the login page
        title.pack(pady=(60, 20)) # pack the title with some padding on top and bottom

        # Server IP field
        ip_label = tk.Label(self, text="Server IP:", font=("Arial", 12), bg="#eaddcf") # the ip\URL input box and label
        ip_label.pack(pady=(5, 0)) # pack the label with some padding on top
        self.ip_entry = tk.Entry(self, font=("Arial", 12), width=25) # the ip\URL input box
        self.ip_entry.insert(0, "books.server") # set the default value of the ip\URL input box
        self.ip_entry.pack(pady=5) # pack the ip\URL input box with some padding on top

        # --- choose a protocol ---
        protocol_label = tk.Label(self, text="Protocol:", font=("Arial", 12), bg="#eaddcf") # the protocol selection buttons and label
        protocol_label.pack(pady=(5, 0)) # pack the label with some padding on top

        self.protocol_var = tk.StringVar(value="TCP") # the protocol selection variable
        radio_frame = tk.Frame(self, bg="#eaddcf") # the radio button frame
        radio_frame.pack(pady=5) # pack the radio button frame with some padding on top
        tk.Radiobutton(radio_frame, text="TCP", variable=self.protocol_var, value="TCP", bg="#eaddcf",
                       font=("Arial", 10)).pack(side="left", padx=10) # create a radio button for TCP and pack it
        tk.Radiobutton(radio_frame, text="RUDP", variable=self.protocol_var, value="RUDP", bg="#eaddcf",
                       font=("Arial", 10)).pack(side="left", padx=10) # create a radio button for RUDP and pack it
        # -------------------------------------

        user_label = tk.Label(self, text="Username:", font=("Arial", 12), bg="#eaddcf") # the username input box and label
        user_label.pack(pady=(5, 0)) # pack the label with some padding on top
        self.username_entry = tk.Entry(self, font=("Arial", 12), width=25) # the username input box
        self.username_entry.pack(pady=5) # pack the username input box with some padding on top

        pass_label = tk.Label(self, text="Password:", font=("Arial", 12), bg="#eaddcf") # the password input box and label
        pass_label.pack(pady=(5, 0)) # pack the label with some padding on top
        self.password_entry = tk.Entry(self, font=("Arial", 12), width=25, show="*") # the password input box
        self.password_entry.pack(pady=5) # pack the password input box with some padding on top

        self.error_label = tk.Label(self, text="", fg="red", bg="#eaddcf", font=("Arial", 10)) # the error label in case of an error
        self.error_label.pack(pady=5) # pack the error label with some padding on top

        login_btn = tk.Button(self, text="Login", font=("Arial", 12, "bold"), bg="cyan", width=15,
                              command=self.check_login) # create the login button
        login_btn.pack(pady=20) # pack the login button with some padding on top

    def check_login(self):
        """A method to check the login credentials and connect to the server."""
        user = self.username_entry.get() # set the user input to a variable
        password = self.password_entry.get() # set the password input to a variable
        server_input = self.ip_entry.get().strip() # set the server input to a variable
        selected_protocol = self.protocol_var.get() # set the selected protocol to a variable

        if not user or not password: # check if the user and password are not empty
            self.error_label.config(text="Please fill in all fields!")
            return

        if not server_input: # check if the server input is not empty
            self.error_label.config(text="Please enter the server IP address!")
            return

        server_ip = server_input # set the server IP to the variable
        if server_input[-1].isalpha(): # in case the server input is a URL, try to resolve it with the DNS server.
            try:
                query = dns.message.make_query(server_input, dns.rdatatype.A) # create a DNS query for the server IP
                response = dns.query.udp(query, "127.0.0.1", timeout=2) # send the query to the local DNS server
                if response.answer: # check if the query was successful
                    server_ip = response.answer[0][0].to_text() # get the IP address from the response
                    print(f"Resolved [DNS] {server_input} to IP: {server_ip}")
                else:
                    # if the query was not successful, display an error message
                    self.error_label.config(
                        text=f"Failed to resolve [DNS] {server_input}. Please check that the server is running.")
                    return
            except Exception as e: # in case of an error, display an error message
                self.error_label.config(text=f"DNS resolution failed for {server_input}: {e}")
                return

        net = self.controller.net_manager # get the network manager instance
        net.host = server_ip # set the server IP to the network manager

        # update the selected protocol
        net.type = selected_protocol

        # reset the socket and assembler
        if net.type == "RUDP":
            import socket
            from RUDPHandle import ChapterAssembler
            net.server_addr = (net.host, net.port) # assign the server address
            net.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # create a UDP socket
            net.assembler = ChapterAssembler() # create a chapter assembler instance
        else:
            net.sock = None  # initialize to None for TCP
            net.assembler = None # not necessary in TCP mode

        # using wrapper function to handle exceptions
        if not net.connect():
            self.error_label.config(text="Server is offline. Cannot connect.")
            return

        # using wrapper function to handle exceptions
        response = net.login(user, password)

        if response == "SUCCESS":
            # if the user is authenticated, show the StartPage
            self.controller.show_frame("StartPage")
        elif response == "FAIL":
            # if the user is not authenticated, display an error message
            self.error_label.config(text="Invalid username or password!")
        else:
            # if the response is not "SUCCESS" or "FAIL", display an error message
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

    # Force a minimum width and height for the card
    card.configure(width=380, height=90)
    card.pack_propagate(False) # prevent the card from shrinking to fit its content

    # Hover effects — change background of card + child labels
    def on_enter(_):
        """A function to change the background color on hover."""
        # noinspection PyShadowingNames
        for widget in (card, title_lbl, desc_lbl):
            widget.configure(bg=hover_color)

    def on_leave(_):
        """A function to change the background color on leave."""
        # noinspection PyShadowingNames
        for widget in (card, title_lbl, desc_lbl):
            widget.configure(bg=bg_color)

    for widget in (card, title_lbl, desc_lbl):
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        widget.bind("<Button-1>", lambda e: command())

    return card


class StartPage(tk.Frame):
    """The main start page of the application. Here the user can choose to request a book from the server or to read a local EPUB file."""
    # Color palette for the gradient theme
    BG_COLOR = "#b2ebf2"       # Mid-tone teal used as the flat fallback
    ACCENT_DARK = "#00695c"  # Dark teal for title text
    ACCENT_MID = "#004d40"  # Darker shade for subtitle
    DIVIDER_COLOR = "#80cbc4"  # Soft teal for decorative elements
    BTN1_BG = "#00897b"  # Request button background
    BTN1_HOVER = "#00695c"  # Request button hover
    BTN2_BG = "#0097a7"  # Read button background
    BTN2_HOVER = "#00838f"  # Read button hover

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # --- Gradient background using a Canvas ---
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bind("<Configure>", self._draw_gradient)

        # --- Content frame (sits on top of canvas, centered) ---
        content = tk.Frame(self, bg="") # create a content frame that will hold all the widgets
        content.place(relx=0.5, rely=0.5, anchor="center") # center the content frame in the window
        content.configure(bg=self.BG_COLOR) # make the content frame background match the gradient mid-tone

        # --- Header section ---
        header = tk.Frame(content, bg=self.BG_COLOR) # create a header frame for the title and subtitle
        header.pack(pady=(20, 10)) # pack the header frame with some padding

        tk.Label(header, text="📚", font=("Arial", 44),
                 bg=self.BG_COLOR).pack() # book emoji as a decorative icon

        tk.Label(header, text="Welcome, Book Worm!",
                 font=("Arial", 26, "bold"), fg=self.ACCENT_DARK,
                 bg=self.BG_COLOR).pack(pady=(8, 2)) # main welcome title

        tk.Label(header, text="Dive into your next adventure",
                 font=("Arial", 14, "italic"), fg=self.ACCENT_MID,
                 bg=self.BG_COLOR).pack() # subtitle text

        tk.Label(header, text="─────────  ♣  ─────────",
                 font=("Arial", 13), fg=self.DIVIDER_COLOR,
                 bg=self.BG_COLOR).pack(pady=(10, 0)) # decorative divider line

        # --- Buttons section ---
        btn_frame = tk.Frame(content, bg=self.BG_COLOR) # create a frame to hold the card buttons
        btn_frame.pack(pady=(25, 10)) # pack the button frame with some padding

        # card button to navigate to the RequestPage (browse and request a book from the server)
        _create_card_button(
            btn_frame,
            title_text="📖  Request a Book",
            desc_text="Browse the library and request a book\nfrom the server to start reading",
            bg_color=self.BTN1_BG,
            hover_color=self.BTN1_HOVER,
            command=lambda: controller.show_frame("RequestPage")
        ).pack(pady=(0, 20))

        # card button to navigate to the ReadPage (load and read a local EPUB file)
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
                 bg=self.BG_COLOR).pack(pady=(30, 15)) # footer label with app name

    # ---- Helpers ----

    # noinspection PyUnusedLocal
    def _draw_gradient(self, event=None):
        """Draw a vertical gradient on the background canvas (top-to-bottom teal)."""
        self.canvas.delete("gradient") # clear any previous gradient lines
        w = self.winfo_width() # get the current width of the window
        h = self.winfo_height() # get the current height of the window
        if w <= 1 or h <= 1: # skip if the window is too small to draw
            return

        # Three-stop gradient color stops: #e0f7fa → #b2ebf2 → #80deea
        colors = [
            (0xe0, 0xf7, 0xfa),  # light top
            (0xb2, 0xeb, 0xf2),  # mid
            (0x80, 0xde, 0xea),  # darker bottom
        ]

        steps = h # one horizontal line per pixel row
        for i in range(steps):
            t = i / max(steps - 1, 1) # normalized position (0.0 to 1.0)
            # Interpolate RGB values across the three color stops
            if t < 0.5:
                local_t = t / 0.5 # normalized position within the first half
                r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * local_t) # interpolate red
                g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * local_t) # interpolate green
                b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * local_t) # interpolate blue
            else:
                local_t = (t - 0.5) / 0.5 # normalized position within the second half
                r = int(colors[1][0] + (colors[2][0] - colors[1][0]) * local_t) # interpolate red
                g = int(colors[1][1] + (colors[2][1] - colors[1][1]) * local_t) # interpolate green
                b = int(colors[1][2] + (colors[2][2] - colors[1][2]) * local_t) # interpolate blue

            hex_color = f"#{r:02x}{g:02x}{b:02x}" # convert RGB to hex color string
            self.canvas.create_line(0, i, w, i, fill=hex_color, tags="gradient") # draw one horizontal line


class RequestPage(tk.Frame):
    """A class representing the Request Page. Here the user can browse the server's book library and select a book to read."""

    def __init__(self, parent, controller):
        super().__init__(parent, bg="seagreen3")
        self.controller = controller # reference to the main application controller

        label = tk.Label(self, text="Request Page", font=("Arial", 25), bg="seagreen3") # the header of the request page
        label.pack(pady=30) # pack the label with some padding

        # Continue Reading section (hidden by default, shown if the user has a saved book)
        self.continue_frame = tk.Frame(self, bg="lightgreen", bd=2, relief="groove") # outer frame for the continue reading section
        self.continue_label = tk.Label(self.continue_frame, text="📖 Continue Reading", font=("Arial", 14, "bold"),
                                       bg="lightgreen") # label for the continue reading section
        self.continue_book_info = tk.Label(self.continue_frame, text="", font=("Arial", 12, "italic"), bg="lightgreen") # label to show the book title and chapter
        self.continue_btn = tk.Button(self.continue_frame, text="▶ Resume Reading", bg="cyan",
                                      font=("Arial", 12, "bold")) # button to resume reading the last book

        self.continue_label.pack(pady=5) # pack the continue reading label
        self.continue_book_info.pack(pady=5) # pack the book info label
        self.continue_btn.pack(pady=10) # pack the resume button

        self.status_label = tk.Label(self, text="Loading books from server...", bg="seagreen3",
                                     font=("Arial", 12, "italic")) # status label to show loading/error messages
        self.status_label.pack(pady=10) # pack the status label

        self.gallery_frame = tk.Frame(self, bg="seagreen3") # frame to hold the book cover gallery
        self.gallery_frame.pack(pady=20) # pack the gallery frame
        self.photos = []  # store PhotoImage references in memory to prevent garbage collection

        tk.Button(self, text="Back to Home", font=("Arial", 12),
                  command=lambda: controller.show_frame("StartPage")).pack(pady=30) # back button to return to StartPage

    def tkraise(self, *args, **kwargs):
        """Called automatically when this page is raised to the top. Refreshes the book list from the server."""
        super().tkraise(*args, **kwargs) # call the parent tkraise method
        self.refresh_book_list() # refresh the book list every time the page is shown

    def refresh_book_list(self):
        """A method to clear the current gallery and fetch a fresh book list from the server."""
        # clear previous screen
        for widget in self.gallery_frame.winfo_children(): # iterate over all widgets in the gallery frame
            widget.destroy() # destroy each widget to clear the gallery
        self.continue_frame.pack_forget() # hide the continue reading section
        self.status_label.config(text="Loading books from server...") # update the status label
        self.photos.clear() # clear the stored photo references

        net = self.controller.net_manager # get the network manager instance

        def fetch_data():
            """Background thread function to fetch the book list and last book from the server."""
            net.stop_reading()  # stop any previous reading session
            last_book = net.get_last_book() # ask the server for the last book the user was reading
            books = net.request_book_list() # request the full list of available books

            # schedule a UI update on the main thread (tkinter is not thread-safe)
            # noinspection PyTypeChecker
            self.after(0, lambda: self._update_ui(last_book, books))

        threading.Thread(target=fetch_data, daemon=True).start() # start the fetch in a background thread

    def _update_ui(self, last_book, books):
        """A method to update the UI with the fetched book list and last book information."""
        # handle the Continue Reading button
        if last_book and last_book[0] != "NONE": # if the user has a saved book
            title, chapter = last_book[0], last_book[1] # extract the book title and chapter index
            self.continue_book_info.config(text=f"\"{title}\" — Chapter {chapter + 1}") # update the book info label
            self.continue_btn.config(command=lambda: self.request_book(title)) # set the resume button to open the saved book
            self.continue_frame.pack(pady=10, before=self.status_label) # show the continue reading section

        if not books: # if the server returned no books
            self.status_label.config(text="No books available on the server.") # update the status label
            return

        self.status_label.config(text="") # clear the status label since books are available

        # create a book gallery from received data
        for i, book in enumerate(books): # iterate over each book in the list
            # noinspection PyBroadException
            try:
                # decode the cover image from Base64
                img_data = base64.b64decode(book['cover']) # decode the base64 string to raw image bytes
                img = Image.open(io.BytesIO(img_data)).resize((100, 130)) # open and resize the image
                photo = ImageTk.PhotoImage(img) # convert to a tkinter-compatible PhotoImage
                self.photos.append(photo) # store in memory to prevent garbage collection

                btn = tk.Button(self.gallery_frame, image=photo, bd=0, cursor="hand2",
                                command=lambda t=book['title']: self.request_book(t)) # create a clickable image button
                btn.grid(row=0, column=i, padx=15, pady=15) # place the button in the gallery grid
            except Exception:
                # fallback: create a text button if the cover image cannot be decoded
                btn = tk.Button(self.gallery_frame, text=book['title'], width=12, height=6, cursor="hand2",
                                command=lambda t=book['title']: self.request_book(t)) # text-only button
                btn.grid(row=0, column=i, padx=15, pady=15) # place the button in the gallery grid

            tk.Label(self.gallery_frame, text=book['title'], bg="seagreen3", font=("Arial", 10, "bold")).grid(row=1,
                                                                                                              column=i) # book title label below each cover

    def request_book(self, book_title):
        """Called when the user clicks a book cover. Requests the book from the server in a background thread."""
        net_manager = self.controller.net_manager # get the network manager instance

        def do_request():
            """Background thread function to request a book and navigate to the ReadPage."""
            net_manager.stop_reading() # stop any previous reading session before starting a new one

            # get the last read chapter before starting the streaming
            saved_chapter = net_manager.get_progress(book_title) # ask the server for saved progress
            if saved_chapter < 0: # if no progress was saved, start from the beginning
                saved_chapter = 0

            # request the book from the server
            success = net_manager.request_book(book_title) # sends the request and receives metadata

            if success:
                # pass the progress to ReadPage and navigate to it
                read_page = self.controller.frames["ReadPage"] # get the ReadPage frame
                read_page.start_reading(net_manager, saved_chapter) # initialize reading with saved progress
                self.controller.show_frame("ReadPage") # switch to the ReadPage
            else:
                import tkinter.messagebox
                tkinter.messagebox.showerror("Error", f"Could not load '{book_title}'") # show an error dialog

        threading.Thread(target=do_request, daemon=True).start() # start the request in a background thread


# noinspection PyTypeChecker
class ReadPage(tk.Frame):
    """A class representing the Read Page. Here the user can read a book chapter by chapter, either from the server or from a local EPUB file."""
    def __init__(self, parent: tk.Widget, controller: BookWormApp) -> None:
        super().__init__(parent)
        self.controller = controller # reference to the main application controller
        self.net_manager = None # will be set when a book is requested from the server
        self.current_page_index = 0 # the index of the currently displayed chapter/page
        self.total_chapters = 0 # total number of chapters in the current book
        self.pages = []  # list of chapter texts for local EPUB reading
        self.reading_mode = None  # reading mode: "server" (streaming from server) or "local" (local EPUB file)
        self.is_hebrew = False  # whether the current book is in Hebrew (used for RTL text direction)

        # --- Font Configuration ---
        self.font_size = 13 # default font size for the text area
        self.font_family = "Georgia" # default font family for the text area

        # List of available fonts for the font selection menu
        self.available_fonts = ["Charter", "Hoefler Text", "Palatino", "Baskerville",
                                "Georgia", "Times New Roman", "Avenir Next", "Helvetica Neue",
                                "Verdana", "Arial", "Courier New", "New Peninim MT", "Comic sans", "Raanana",
                                "Arial Hebrew"]

        # --- Themes Configuration ---
        self.themes = [
            {"name": "Sepia", "bg": "#eaddcf", "fg": "black", "text_bg": "#eaddcf"}, # warm sepia theme
            {"name": "Dark Mode", "bg": "#2b2b2b", "fg": "white", "text_bg": "#333333"}, # dark mode theme
            {"name": "Light Mode", "bg": "white", "fg": "black", "text_bg": "white"} # light mode theme
        ]
        self.current_theme_index = 0 # index of the currently active theme

        self.configure(bg=self.themes[0]["bg"]) # set the initial background color

        # --- Header ---
        self.header = tk.Label(self, text="Reading Room", font=("Arial", 14)) # the header label
        self.header.pack(pady=5) # pack the header with some padding

        # --- Top Controls Frame (font size, theme, font family) ---
        top_controls = tk.Frame(self, bg=self.themes[0]["bg"]) # frame to hold the top control buttons
        top_controls.pack(pady=5) # pack the top controls frame
        self.top_controls_frame = top_controls # store a reference for theme updates

        # 1. Decrease Font Button
        self.btn_minus = tk.Button(top_controls, text="A-", width=3,
                                   command=lambda: self.change_font_size(-2)) # button to decrease font size by 2
        self.btn_minus.pack(side="left", padx=5) # pack the button to the left

        # 2. Theme Button
        self.theme_btn = tk.Button(top_controls, text="🎨 Theme",
                                   command=self.toggle_theme, bg="gold") # button to cycle through themes
        self.theme_btn.pack(side="left", padx=5) # pack the button to the left

        # 3. Font Family Button
        self.btn_font = tk.Button(top_controls, text="🔤 Font", bg="lightblue") # button to open font selection menu
        self.btn_font.pack(side="left", padx=5) # pack the button to the left

        # Create the popup menu for fonts
        self.font_menu = tk.Menu(self, tearoff=0) # create a dropdown menu (no tearoff)
        for f in self.available_fonts: # add each font as a menu item
            self.font_menu.add_command(label=f, command=lambda font=f: self.change_font_family(font))

        # Bind the left mouse click to show the font menu
        self.btn_font.bind("<Button-1>", self.do_popup)

        # 4. Increase Font Button
        self.btn_plus = tk.Button(top_controls, text="A+", width=3,
                                  command=lambda: self.change_font_size(2)) # button to increase font size by 2
        self.btn_plus.pack(side="left", padx=5) # pack the button to the left

        # --- Main Text Area ---
        self.text_area = tk.Text(self, wrap="word",
                                 font=(self.font_family, self.font_size),
                                 padx=40, pady=20, borderwidth=0) # scrollable text widget for displaying chapter content
        self.text_area.pack(expand=True, fill="both") # expand to fill all available space

        # --- Navigation Bar ---
        self.nav_frame = tk.Frame(self) # frame to hold the navigation buttons and page label
        self.nav_frame.pack(fill="x", pady=10) # pack the nav frame horizontally

        self.btn_prev = tk.Button(self.nav_frame, text="◀ Prev", command=self.prev_page) # button to go to the previous chapter
        self.btn_prev.pack(side="left", padx=50) # pack the button to the left with padding

        self.page_label = tk.Label(self.nav_frame, text="Page 0 of 0") # label to display the current page/chapter number
        self.page_label.pack(side="left", expand=True) # pack the label in the center

        self.btn_next = tk.Button(self.nav_frame, text="Next ▶", command=self.next_page) # button to go to the next chapter
        self.btn_next.pack(side="right", padx=50) # pack the button to the right with padding

        # --- Footer Controls ---
        controls_frame = tk.Frame(self) # frame to hold the footer control buttons
        controls_frame.pack(pady=5) # pack the footer controls frame

        tk.Button(controls_frame, text="Home",
                  command=self.go_home).pack(side="left", padx=5) # button to save progress and return to the start page

        tk.Button(controls_frame, text="📂 Load EPUB",
                  command=self.load_epub).pack(side="left", padx=5) # button to open a local EPUB file

        self.loading_label = tk.Label(self, text="", font=("Arial", 10, "italic")) # label to show loading/buffer status
        self.loading_label.pack(pady=2) # pack the loading label

        self.apply_theme() # apply the default theme to all widgets

    def start_reading(self, net_manager, start_chapter=0):
        """Called when a book is successfully requested from the server. Initializes server reading mode."""
        self.reading_mode = "server" # set reading mode to server streaming
        self.net_manager = net_manager # store the network manager reference
        self.current_page_index = start_chapter # set the current page to the saved progress instead of 0
        self.total_chapters = net_manager.total_chapters # store the total number of chapters
        self.is_hebrew = self._contains_hebrew(net_manager.book_title) # detect if the book is in Hebrew for RTL support
        self.net_manager.notify_user_advanced(self.current_page_index) # notify the network manager so the prefetch loop knows we jumped ahead
        net_manager.on_chapter_ready = self._on_chapter_ready # set callback: when a chapter arrives, refresh if needed
        self.after(100, self._try_display_current) # wait briefly for the first chapter, then attempt to display

    def _on_chapter_ready(self, chapter_index: int):
        """Called from the prefetch thread when a new chapter is buffered."""
        # use `after` to safely update the UI from the main thread (tkinter is not thread-safe)
        if chapter_index == self.current_page_index: # only refresh if the buffered chapter is the one we need
            self.after(0, self._try_display_current)

    def _try_display_current(self):
        """Attempt to display the current chapter from the buffer. Retries if not yet available."""
        if not self.net_manager: # guard: no network manager means nothing to display
            return

        text = self.net_manager.get_chapter(self.current_page_index) # try to get the chapter text from the buffer
        if text is not None: # if the chapter is available in the buffer
            self.loading_label.config(text="") # clear the loading message
            self._display_chapter(text) # render the chapter in the text area
        else:
            self.loading_label.config(text="Loading chapter...") # show a loading message
            self.after(200, self._try_display_current) # retry in 200ms

    def _display_chapter(self, full_text: str):
        """Render a chapter in the text area, with title styling and RTL support."""
        self.text_area.config(state="normal") # enable editing to insert new content
        self.text_area.delete('1.0', tk.END) # clear the text area

        # split the chapter text into a title (first line) and body (rest)
        if '\n' in full_text:
            title_text, body_text = full_text.split('\n', 1) # split on the first newline
        else:
            title_text = full_text # if no newline, the entire text is the title
            body_text = ""

        self.text_area.insert(tk.END, title_text + "\n") # insert the title text
        self.update_title_style() # configure the title style tag
        self.text_area.tag_add("title_style", "1.0", "1.end") # apply the title style to the first line
        self.text_area.insert(tk.END, body_text) # insert the body text
        self._apply_rtl_direction() # apply RTL direction if the book is in Hebrew

        self.text_area.config(state="disabled") # disable editing to prevent user modification
        self.page_label.config(text=f"Chapter {self.current_page_index + 1} of {self.total_chapters}") # update the page label
        self.text_area.yview_moveto(0) # scroll to the top of the text area

        # show buffer status to the user
        buffered = self.net_manager.next_server_index - self.current_page_index # calculate how many chapters are buffered ahead
        self.loading_label.config(text=f"📦 {buffered} chapter(s) buffered ahead") # display the buffer status

    def _save_current_progress(self):
        """Save the user's current reading progress to the server."""
        if self.reading_mode == "server" and self.net_manager and self.net_manager.book_title: # only save if we are in server mode and have a valid book
            self.net_manager.save_progress(self.net_manager.book_title, self.current_page_index) # send progress to the server

    def go_home(self):
        """Stop reading, save progress, and go back to the start page."""
        if self.reading_mode == "server" and self.net_manager: # only save and stop if we are in server mode
            self._save_current_progress() # save the current reading progress
            self.net_manager.stop_reading() # stop the streaming and prefetch threads
        self.controller.show_frame("StartPage") # navigate back to the start page

    def next_page(self):
        """Advance to the next page/chapter (works for both server and local modes)."""
        if self.reading_mode == "server":
            if self.current_page_index < self.total_chapters - 1: # check if there is a next chapter
                self.current_page_index += 1 # move to the next chapter
                self.net_manager.notify_user_advanced(self.current_page_index) # notify the prefetch loop that we moved forward
                self._save_current_progress() # save progress to the server
                self._try_display_current() # attempt to display the new chapter
        elif self.reading_mode == "local":
            if self.current_page_index < len(self.pages) - 1: # check if there is a next page
                self.current_page_index += 1 # move to the next page
                self.update_page() # render the new page

    def prev_page(self):
        """Go back to the previous page/chapter (works for both server and local modes)."""
        if self.current_page_index > 0: # check if there is a previous chapter/page
            self.current_page_index -= 1 # move to the previous chapter/page
            if self.reading_mode == "server":
                self.net_manager.notify_user_advanced(self.current_page_index) # notify the prefetch loop that we moved back
                self._save_current_progress() # save progress to the server
                self._try_display_current() # attempt to display the new chapter
            elif self.reading_mode == "local":
                self.update_page() # render the new page

    # --- HELPER: Update the Title Tag Style ---
    def update_title_style(self):
        """Configures the 'title_style' tag. Updates whenever the font size, family, or theme changes."""
        current_fg = self.themes[self.current_theme_index]["fg"] # get the foreground color from the current theme

        self.text_area.tag_configure("title_style",
                                     font=(self.font_family, self.font_size + 3, "bold"),  # size + 3 and bold
                                     justify='right' if self.is_hebrew else 'center',  # RTL for Hebrew, center otherwise
                                     underline=True,  # underline the title
                                     foreground=current_fg  # match the theme's text color
                                     )

    # --- Functions ---
    def do_popup(self, event):
        """Show the font selection popup menu at the mouse cursor position."""
        try:
            self.font_menu.tk_popup(event.x_root, event.y_root) # display the popup menu at the click location
        finally:
            self.font_menu.grab_release() # release the grab so other widgets can receive events

    def change_font_family(self, new_family):
        """Change the font family of the text area and update the title style."""
        self.font_family = new_family # store the new font family
        self.text_area.configure(font=(self.font_family, self.font_size)) # apply the new font to the text area
        self.update_title_style() # update title style to match the new font family

    def change_font_size(self, delta):
        """Change the font size of the text area by delta (positive or negative). Clamped to 8-40."""
        new_size = self.font_size + delta # calculate the new font size
        if 8 <= new_size <= 40: # clamp the font size to a reasonable range
            self.font_size = new_size # store the new font size
            self.text_area.configure(font=(self.font_family, self.font_size)) # apply the new font size to the text area
            self.update_title_style() # update the title style to match the new size

    def toggle_theme(self):
        """Cycle to the next theme in the list and apply it."""
        self.current_theme_index += 1 # move to the next theme index
        if self.current_theme_index >= len(self.themes): # wrap around if we've reached the end
            self.current_theme_index = 0
        self.apply_theme() # apply the new theme

    @staticmethod
    def _contains_hebrew(text: str) -> bool:
        """Check if a string contains Hebrew characters (Unicode block 0x0590-0x05FF)."""
        return any('\u0590' <= ch <= '\u05FF' for ch in text) # return True if any character is in the Hebrew Unicode range

    def _apply_rtl_direction(self):
        """Configure the text area for RTL (Hebrew) or LTR display."""
        if self.is_hebrew: # if the book is in Hebrew
            self.text_area.tag_configure("rtl", justify="right") # set text justification to right
            self.text_area.tag_add("rtl", "1.0", tk.END) # apply the RTL tag to all text
        else:
            self.text_area.tag_remove("rtl", "1.0", tk.END) # remove the RTL tag for LTR text

    def apply_theme(self):
        """Apply the currently selected theme to all widgets on the ReadPage."""
        theme = self.themes[self.current_theme_index] # get the current theme dictionary
        bg_color = theme["bg"] # background color
        fg_color = theme["fg"] # foreground (text) color
        text_bg = theme["text_bg"] # text area background color

        self.configure(bg=bg_color) # apply background to the main frame
        self.header.configure(bg=bg_color, fg=fg_color) # apply theme to the header label
        self.text_area.configure(bg=text_bg, fg=fg_color, insertbackground=fg_color) # apply theme to the text area
        self.nav_frame.configure(bg=bg_color) # apply background to the navigation frame
        self.page_label.configure(bg=bg_color, fg=fg_color) # apply theme to the page label
        self.top_controls_frame.configure(bg=bg_color) # apply background to the top controls frame

        self.update_title_style() # update the title color to match the new theme

    def load_epub(self):
        """Open a file dialog to load a local .epub file and switch to local reading mode."""
        file_path = filedialog.askopenfilename(filetypes=[("EPUB files", "*.epub")]) # open a file dialog to select an EPUB file
        if not file_path: return # if the user canceled the dialog, do nothing

        try:
            book = epub.read_epub(file_path) # parse the EPUB file using ebooklib
            self.pages = [] # reset the pages list
            for item in book.get_items(): # iterate over all items in the EPUB
                if item.get_type() == ebooklib.ITEM_DOCUMENT: # only process document items (chapters)
                    soup = BeautifulSoup(item.get_content(), 'html.parser') # parse the HTML content
                    text = soup.get_text().strip() # extract plain text from the HTML
                    if text: # only add non-empty chapters
                        self.pages.append(text)
            self.reading_mode = "local" # switch to local reading mode
            self.current_page_index = 0 # start from the first page
            self.total_chapters = len(self.pages) # store the total number of pages
            # Detect Hebrew from the file name
            import os
            self.is_hebrew = self._contains_hebrew(os.path.basename(file_path)) # check if the file name contains Hebrew characters
            self.update_page() # render the first page
        except Exception as e:
            import tkinter
            tkinter.messagebox.showerror("Error", f"Failed to load EPUB file: {e}") # show an error dialog if loading fails

    def update_page(self):
        """Render the current page for local EPUB reading mode."""
        if not self.pages: return # guard: do nothing if there are no pages

        self.text_area.config(state="normal") # enable editing to insert new content
        self.text_area.delete('1.0', tk.END) # clear the text area

        full_text = self.pages[self.current_page_index] # get the text of the current page

        # Split text into Title (first line) and Body (rest)
        if '\n' in full_text:
            title_text, body_text = full_text.split('\n', 1) # split on the first newline
        else:
            title_text = full_text # if no newline, the entire text is the title
            body_text = ""

        # 1. Insert Title
        self.text_area.insert(tk.END, title_text + "\n") # insert the title text

        # 2. Apply the 'title_style' tag to the first line
        self.update_title_style() # configure the title style tag
        self.text_area.tag_add("title_style", "1.0", "1.end") # apply the title style to the first line

        # 3. Insert the rest of the body
        self.text_area.insert(tk.END, body_text) # insert the body text
        self._apply_rtl_direction() # apply RTL direction if the book is in Hebrew

        self.text_area.config(state="disabled") # disable editing to prevent user modification
        self.page_label.config(text=f"Page {self.current_page_index + 1} of {len(self.pages)}") # update the page label
        self.text_area.yview_moveto(0) # scroll to the top of the text area


if __name__ == "__main__":
    app = BookWormApp()
    app.mainloop()
