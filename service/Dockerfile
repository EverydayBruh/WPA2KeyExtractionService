# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /usr/src/app

RUN apt-get update && \
    apt-get install -y hashcat && \
    apt-get install -y hcxtools && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the application
CMD ["./wait-for-it.sh", "rabbitmq:5672", "--", "python", "-u", "./processor.py"]