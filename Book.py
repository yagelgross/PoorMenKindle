class Book:
    def __init__(self, title, author, chapterCount, path, coverPath=None):
        self.title = title
        self.author = author
        self.chapterCount = chapterCount
        self.path = path
        self.fileType = self.path.split(".")[-1]
        self.coverPath = coverPath  # path to a PNG/JPG/JPEG cover image, or None