# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the application
CMD ["./wait-for-it.sh", "rabbitmq:5672", "--", "python", "-u", "./worker.py"]
