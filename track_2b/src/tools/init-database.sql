\getenv runtime_password APP_DATABASE_PASSWORD
\getenv keycloak_password KEYCLOAK_DATABASE_PASSWORD
CREATE ROLE continuity_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'runtime_password';
CREATE ROLE keycloak_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'keycloak_password';
CREATE DATABASE keycloak OWNER keycloak_owner;
REVOKE CONNECT ON DATABASE continuity FROM PUBLIC;
GRANT CONNECT ON DATABASE continuity TO continuity_owner, continuity_app;
REVOKE CONNECT ON DATABASE keycloak FROM PUBLIC;
GRANT CONNECT ON DATABASE keycloak TO continuity_owner, keycloak_owner;
