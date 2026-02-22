import socket
import Client
import Book
import threading

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

def EpubHandler