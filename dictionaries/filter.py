# Имя файла с паролями
filename = 'rockyou.txt'

# Читаем все пароли из файла
with open(filename, 'r') as file:
    passwords = file.readlines()

# Фильтруем пароли, оставляя только те, которые имеют 8 или более символов
filtered_passwords = [password.strip() for password in passwords if len(password.strip()) >= 8]

# Записываем отфильтрованные пароли обратно в файл
with open(filename, 'w') as file:
    for password in filtered_passwords:
        file.write(password + '\n')

print(f"Пароли короче 8 символов удалены. Результат сохранен в {filename}")
