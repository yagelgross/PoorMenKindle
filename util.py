def Caesar_cipher(string: str, shift: int) -> str:
    """A function to shift characters in a string by a given amount. The point is to provide
     simple encryption for the usernames and passwords when they pass through the network.
     This is not a secure encryption method, not even close, but it is better than nothing."""
    result = ""
    for char in string: # we only shift letters and digits, other characters are left unchanged
        if char.isalpha(): # if the character is a letter, shift it in the alphabet
            shift_amount = shift % 26 # ensure that the shift amount is logical (i.e., not greater than 26)
            if char.islower():
                #if the char is lower case, shift it using the value of 'a'.
                shifted_char = chr((ord(char) - ord('a') + shift_amount) % 26 + ord('a'))
            else:
                #if the char is upper case, shift it using the value of 'A'.
                shifted_char = chr((ord(char) - ord('A') + shift_amount) % 26 + ord('A'))
            result += shifted_char # update the result string with the shifted character
        elif char.isdigit():
            # if the character is a digit, shift it in the range 0-9
            shift_amount = shift % 10
            # shift the digit using the value of '0'
            shifted_char = chr((ord(char) - ord('0') + shift_amount) % 10 + ord('0'))
            result += shifted_char
        else:
            result += char # if the character is not a letter or digit, leave it unchanged

    return result

def Caesar_decipher(string: str, shift: int) -> str:
    """Decipher a string encrypted with Caesar cipher."""
    return Caesar_cipher(string, -shift) # decrypt by negating the shift amount