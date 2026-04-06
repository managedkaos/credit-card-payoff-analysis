# Use an official Python runtime as a parent image
FROM python:3.13-slim
ENV WORKDIR=/work
RUN mkdir /work

# Set the working directory in the container
WORKDIR ${WORKDIR}

# Install runtime dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy necessary files
COPY main.py /usr/local/bin

# Run the script when the container launches
ENTRYPOINT ["python", "/usr/local/bin/main.py"]
