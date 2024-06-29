def read_specific_line(file_path, line_number):
    with open(file_path, 'r', encoding='utf-8') as file:
        for current_line_number, line in enumerate(file, start=1):
            if current_line_number == line_number:
                return line.strip()
    return None

# Пример использования
file_path = 'BIG-WPA-LIST-1'
line_number = 123456  # номер строки, которую хотите прочитать
password = read_specific_line(file_path, line_number)

if password:
    print(f"Password at line {line_number}: {password}")
else:
    print(f"Line {line_number} not found.")
