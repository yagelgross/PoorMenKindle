def ceasar_cipher(string: str, shift: int) -> str:
    result = ""
    for char in string:
        if char.isalpha():
            shift_amount = shift % 26
            if char.islower():
                shifted_char = chr((ord(char) - ord('a') + shift_amount) % 26 + ord('a'))
            else:
                shifted_char = chr((ord(char) - ord('A') + shift_amount) % 26 + ord('A'))
            result += shifted_char
        elif char.isdigit():
            shift_amount = shift % 10
            shifted_char = chr((ord(char) - ord('0') + shift_amount) % 10 + ord('0'))
            result += shifted_char
        else:
            result += char

    return result

def ceasar_decipher(string: str, shift: int) -> str:
    return ceasar_cipher(string, -shift)