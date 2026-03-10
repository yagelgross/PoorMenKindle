class Client:
    """An object to represent the clients in the server. In order to support multiple users, we needed a
     convenient way to store their information and access data. For added functionality and convenience, we added the last
     location the client was on every book he read, and the last book he read in itself."""
    def __init__(self, userName, password, isAdmin):
        """A constructor for the Client class."""
        self.UserName = userName
        self.Password = password
        self.isAdmin = isAdmin
        self.lastBookRead = None          # title of the last book opened
        self.allBooksRead = {}            # { bookTitle: lastChapterIndex }

    def getCurrChapter(self, bookTitle):
        """Return the last chapter the user was on for this book, or -1 if never read."""
        return self.allBooksRead.get(bookTitle, -1)

    def setCurrChapter(self, bookTitle, chapter):
        """Set the last chapter the user was reading for this book."""
        self.allBooksRead[bookTitle] = chapter #Save reading progress for a book.
        self.lastBookRead = bookTitle # update the last book the client was reading.

    def getUserName(self):
        """Return the username of the client."""
        return self.UserName

    def getPassword(self):
        """Return the password of the client."""
        return self.Password