FROM python:3.12-alpine

# Add your application
COPY ./main.py /app/main.py
COPY ./.env /app/.env

# Copy and enable your CRON task
COPY ./crontask /app/crontask
RUN crontab /app/crontask

# Create empty log (TAIL needs this)
RUN touch /tmp/out.log

# Start TAIL - as your always-on process (otherwise - container exits right after start)
CMD crond && tail -f /tmp/out.log
