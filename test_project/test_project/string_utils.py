def reverse_string(s: str) -> str:
    """Returns the reversed version of the input string."""
    return s[::-1]


def count_vowels(s: str) -> int:
    """Counts the number of vowels in the input string."""
    return sum(1 for char in s.lower() if char in 'aeiou')


def is_palindrome(s: str) -> bool:
    """Checks if the input string is a palindrome."""
    cleaned_str = ''.join(char.lower() for char in s if char.isalnum())
    return cleaned_str == cleaned_str[::-1]