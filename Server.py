import socket
from typing import Any

import Client
import Book
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


currClients: list[Client] = []
availableBooks = [Book.Book("Eragon", "Cristopher Paolini", 50,
                           "/booksForServer/Eragon.epub"),
                Book.Book("Eldest", "Cristopher Paolini", 83,
                           "/booksForServer/Eldest.epub"),
                Book.Book("Brisingr", "Cristopher Paolini", 68,
                           "/booksForServer/Brisingr.epub"),
                Book.Book("Inheritance", "Cristopher Paolini", 88,
                           "/booksForServer/Inheritance.epub"),
                ]
AllClients = [Client.Client("Yagel", "123456", True),
            Client.Client("Noam", "123456", True),
            Client.Client("Taltul", "123456", False)]
Yagel = AllClients[0]
Noam = AllClients[1]
adminClients = [Yagel, Noam]

class server:


    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.bind(('', 12345))
    serverSocket.listen(1)

    def epub_handler (bookname):
        try:
            path = "booksForServer/" + bookname + ".epub"
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

    def validate_user(userName, password):
        for client in AllClients:
            if client.getUserName() == userName and client.getPassword() == password:
                currClients.append(client)
                for client in currClients:
                    print(client.getUserName())
                return True
        return False

    def get_available_books(self):
        book_titles = []
        for book in availableBooks:
            book_titles.append(book.title)
        return book_titles

    while True:
        conn, addr = serverSocket.accept()
        print("Client connected from:", addr)
        try:
            data = conn.recv(1024).decode('utf-8')
            if not data:
                continue

            parts = data.split('|')
            if len(parts) == 3 and parts[0] == "LOGIN":
                username = parts[1]
                password = parts[2]
                if validate_user(username, password):
                    conn.send("SUCCESS".encode())

                else:
                    conn.send("FAIL".encode())
                    conn.close()
                    continue

            else:
                conn.send("Invalid username or password. Connection will be closed.".encode())
                conn.close()
        except Exception as e:
            print(f"Error handling client: {e}")

