import Book

class Client:
    lastBookRead = None
    allBooksRead = {}
    UserName = None
    Password = None
    isAdmin = False

    def __init__(self, userName, password, isTrue):
        self.UserName = userName
        self.Password = password
        self.isAdmin = isTrue

    def getCurrChapter(self, Book):
        return self.allBooksRead[Book]

    def setCurrChapter(self, Book, chapter):
        self.allBooksRead[Book] = chapter

    def getUserName(self):
        return self.UserName

    def getPassword(self):
        return self.Password