class Book:
    def __init__(self, title, author, chapterCount, path):
        self.title = title
        self.author = author
        self.chapterCount = chapterCount
        self.path = path
        self.fileType = self.path.split(".")[-1]
