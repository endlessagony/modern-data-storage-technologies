FROM trinodb/trino:483

USER root
ADD https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar /tmp/postgresql-42.7.3.jar
RUN install -m 644 /tmp/postgresql-42.7.3.jar /usr/lib/trino/plugin/iceberg/postgresql-42.7.3.jar \
    && rm /tmp/postgresql-42.7.3.jar
USER trino
