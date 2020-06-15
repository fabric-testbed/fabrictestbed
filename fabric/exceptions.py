class TokenExpiredException(Exception):
    def __init__(self, text, data=None):
        super(TokenExpiredException, self).__init__()
        self.text = str(text)
        self.data = data

    def __str__(self):
        return self.text
