# We will use python:3.10-alpine as the base image for building the Flask container
FROM python:3.10-alpine
# It specifies the working directory where the Docker container will run
WORKDIR /app
# Copying all the application files to the working directory
COPY ./requirements.txt /app/requirements.txt
# Install all the dependencies required to run the Flask application
RUN pip install -r /app/requirements.txt
# Expose the Docker container for the application to run on port 5000
COPY ./app.py /app/app.py
# copy command to run the healthcheck, ensure the health file is created
COPY ./healthcheck.py /app/healthcheck.py
RUN touch /app/health
# The command required to run the Dockerized application
EXPOSE 5000
# show print
ENV PYTHONUNBUFFERED=1
# run the app
CMD ["python", "/app/app.py"]
