import socket
import Client
import Book
import threading
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


currClients = []
availableBooks = [Book.Book("Eragon", "Cristopher Paolini", 50,
                            "/booksForServer/Eragon.epub"),
                  Book.Book("Eldest", "Cristopher Paolini", 83,
                            "/booksForServer/Eldest.epub"),
                  Book.Book("Brisingr", "Cristopher Paolini", 68,
                            "/booksForServer/Brisingr.epub"),
                  Book.Book("Inheritance", "Cristopher Paolini", 88,
                            "/booksForServer/Inheritance.epub"),
                  ]
AllClients = [Client.Client("Yagel", "089756", True),
              Client.Client("Noam", "123456", True),
              Client.Client("Taltul", "123456", False)]
Yagel = AllClients[0]
Noam = AllClients[1]
adminClients = [Yagel, Noam]

serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serverSocket.bind(('', 12345))
serverSocket.listen(5)

def EpubHandler (Bookname):
    try:
        path = "booksForServer/" + Bookname + ".epub"
        book = epub.read_epub(path)
        chapters = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html_content = item.get_content()
                soup = BeautifulSoup(html_content, 'html.parser')
                text_content = soup.get_text(separator='\n\n', strip=True)
                if text_content:
                    chapters.append(text_content)
        return chapters

    except Exception as e:
        print("Please ensure the book exists in the server's book directory and is in .epub format.")
        return None

