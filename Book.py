class Book:
    def __init__(self, title, author, pageCount, path):
        self.title = title
        self.author = author
        self.pageCount = pageCount
        self.path = path
        self.fileType = self.path.split(".")[-1]
