class Client:
    def __init__(self, userName, password, isAdmin):
        self.UserName = userName
        self.Password = password
        self.isAdmin = isAdmin
        self.lastBookRead = None          # title of the last book opened
        self.allBooksRead = {}            # { bookTitle: lastChapterIndex }

    def getCurrChapter(self, bookTitle):
        #Return the last chapter the user was on for this book, or -1 if never read.
        return self.allBooksRead.get(bookTitle, -1)

    def setCurrChapter(self, bookTitle, chapter):
        self.allBooksRead[bookTitle] = chapter #Save reading progress for a book.
        self.lastBookRead = bookTitle

    def getUserName(self):
        return self.UserName

    def getPassword(self):
        return self.Password