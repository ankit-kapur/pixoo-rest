from app import split_into_lines

if __name__ == '__main__':
    wholeText = "Hello, this is a whole sentence. Should truncate with ellipsis when it goes beyond the maximum screen size. And words should be on the same line unless a word is too big for a line."
    result = split_into_lines(wholeText)

    print(str(result))