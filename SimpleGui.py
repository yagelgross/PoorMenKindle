import tkinter as tk
from tkinter import font as tkfont

class BookWormApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("♣BookWormHole♣")
        self.geometry('600x800')
        self.resizable(False, False)

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
        super().__init__(parent, bg="khaki")
        label = tk.Label(self, text="Reading Room", font=("Arial", 25), bg="khaki")
        label.pack(pady=100)

        back_btn = tk.Button(self, text="Back to Home",
                             command=lambda: controller.show_frame("StartPage"))
        back_btn.pack()

if __name__ == "__main__":
    app = BookWormApp()
    app.mainloop()