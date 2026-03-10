class Book:
    """ An object to represent a book with its metadata. The path should be the relative
     path to the book file on the server, and the coverPath should be the relative path to
     a PNG/JPG/JPEG cover image (or None if no cover)."""
    def __init__(self, title, author, chapterCount, path, coverPath=None):
        """The constructor for the Book class."""
        self.title = title # the book's title
        self.author = author # the book's author'
        self.chapterCount = chapterCount # how many chapters are in the book
        self.path = path # where the book is located on the server
        self.fileType = self.path.split(".")[-1] # the file type of the book (pdf, word, epub et cetera, only epub for the project's purposes)
        self.coverPath = coverPath  # path to a PNG/JPG/JPEG cover image, or None if there is no such image