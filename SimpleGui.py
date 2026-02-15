# Import Module
from tkinter import *

fontsize = 20
x = 1
root = Tk()

root.title("♣BookWormHole♣")
root.geometry('600x800')
root.resizable(False, False)
title1 = Label(root, text = "Are you a Book Worm?",font=("Arial", fontsize, "bold"),bg="cyan3")
title2 = Label(root, text ="If so, you can read your books here!", font=("Arial", fontsize, "bold"),bg="cyan3")
title1.grid(row=0,column=0,padx=140,pady=30)
title2.grid(row=1, column=0)
def clickedReq():
    print("You clicked the Req button")

def clickedRead():
    print("You clicked the Read button")

requestButton = Button(root, text ="Request a Book",
                       fg = "blue", command=clickedReq,bg = "cyan",bd=10,relief="groove")
requestButton.grid(column=0, row=3,pady=100)
requestButton.config(width=40,height=8)

readButton = Button(root, text ="Read a Book",
                       fg = "blue", command=clickedRead,bg = "cyan",bd=10,relief="groove")

readButton.grid(column=0, row=4)
readButton.config(width=40,height=8)

root.configure(bg="lightblue")

root.mainloop()