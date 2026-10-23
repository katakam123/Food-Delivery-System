# Food Delivery System

A backend application for managing food delivery workflows, including customers, restaurants, menu items, carts, orders, coupons, delivery partners, and order tracking.

## Overview

This project provides REST APIs built with FastAPI and uses MySQL for persistent storage. Docker Compose runs the API and database as separate services.

## Technology Stack

- Python 3.12 (Docker image)
- FastAPI
- Pydantic
- SQLAlchemy
- MySQL 8
- Alembic database migrations
- JWT authentication
- Uvicorn
- Docker and Docker Compose
- Pytest for automated tests

> Confirm the final list against the dependencies and features implemented in this repository.

## Features

The project is designed to support the following workflows, subject to the implemented API:

- User registration, login, and authentication
- Role-based access for customers, administrators, restaurant owners, and delivery partners
- Restaurant and menu management
- Customer addresses and shopping carts
- Order creation and status management
- Coupons and discount validation
- Delivery partner availability and assignment
- Delivery status and tracking
- Delivery fee calculation and peak-hour pricing
- Scheduled orders
- Database migrations
- Automated tests

Only mark a feature as complete when it has been implemented and tested.

## Project Structure

```text
food_delivery_system/
├── app/
│   ├── main.py
│   ├── models/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   ├── utils/
│   └── jobs/
├── alembic/
├── tests/
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .env.example
└── README.md
```

Adjust this tree to match the files and directories that actually exist in your repository.

## Prerequisites

- Git
- Docker Desktop
- Docker Compose
- A web browser for Swagger UI

A local Python installation is not required to run the application through Docker.

## Configuration

1. Create a local `.env` file in the project root.
2. Configure the database credentials, JWT secret, and any other required application settings.
3. Use strong, unique secrets. Do not commit `.env` to GitHub.
4. Make sure `.env.example` contains only placeholder values, never real credentials.

Example configuration:

```dotenv
MYSQL_DATABASE=food_delivery
MYSQL_USER=foodapp
MYSQL_PASSWORD=replace_with_a_strong_password
MYSQL_ROOT_PASSWORD=replace_with_a_different_strong_password

JWT_SECRET_KEY=replace_with_a_long_random_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Keep any additional environment variables required by your application. The variable names in this example must match those used by your Docker Compose file and application settings.

## Run with Docker Compose

From the project root, build and start the application:

```powershell
docker compose up --build
```

Check the container status in a second terminal:

```powershell
docker compose ps
```

View API logs:

```powershell
docker compose logs --tail=100 api
```

View database logs:

```powershell
docker compose logs --tail=100 mysql
```

Stop the containers with:

```powershell
docker compose down
```

The named MySQL volume is intended to preserve database data when containers are stopped or removed. Do not use `docker compose down -v` unless you intentionally want to remove the database volume.

## API Documentation

After the API starts, open:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI schema: http://localhost:8000/openapi.json

The available endpoints and authentication requirements are defined by the running application.

## Run Automated Tests

If the test suite and dependencies are configured, run:

```powershell
python -m pytest -v
```

To run a particular test file:

```powershell
python -m pytest tests/test_pricing.py -v
```

Run the commands in your local virtual environment, or execute tests inside the API container if the image contains the test dependencies and test files.

Document the actual test results before submission. Do not claim that tests pass until they have been executed successfully.

## Database Migrations

Review migration status and history using your project's Alembic configuration:

```powershell
python -m alembic current
python -m alembic history
```

Apply pending migrations using the configured database connection:

```powershell
python -m alembic upgrade head
```

The Docker startup command may already apply migrations. Avoid generating or applying duplicate migrations without checking the current migration history.

## Security Notes

- Never commit `.env`, access tokens, passwords, private keys, or production database dumps.
- Use strong JWT secrets and rotate any secret that has been exposed.
- Keep database credentials out of source code.
- Validate request data and enforce authorization on every protected operation.
- Verify that customers cannot access another customer's addresses, carts, orders, or private data.
- Restrict administrative operations to authorized roles.
- Validate file types and file sizes if uploads are supported.
- Use HTTPS and secure secret management when deploying publicly.
- Keep dependencies updated and review security advisories.
- Do not expose MySQL publicly in a production deployment unless there is a specific, secured requirement.

## Testing Checklist

- [ ] Customer registration and login
- [ ] Authentication and invalid-token handling
- [ ] Role-based authorization
- [ ] Restaurant and menu CRUD operations
- [ ] Cart totals and quantity validation
- [ ] Coupon validity, expiry, and usage limits
- [ ] Order creation, cancellation, and status transitions
- [ ] Delivery partner assignment and offer timeouts
- [ ] Delivery OTP validation, if implemented
- [ ] Delivery fee and peak-hour pricing
- [ ] Scheduled order validation, if implemented
- [ ] Database migrations
- [ ] Invalid IDs, missing fields, and unauthorized requests
- [ ] Docker startup and API health

## Troubleshooting

**API cannot connect to MySQL**

- Check that the MySQL container is healthy.
- Check that the API uses the Compose service hostname `mysql`, not `localhost`, for its database connection.
- Verify database name, username, password, and port configuration.

**Port 8000 is already in use**

- Stop the conflicting service or change the host-side port mapping in Docker Compose.

**Migration failure**

- Inspect the Alembic traceback and database configuration.
- Verify that all model modules are imported by the migration environment.
- Do not delete the database as a first troubleshooting step.

**API returns an error**

- Review the API logs and the response body in Swagger UI.
- Check request schemas, authentication, permissions, and database constraints.

## Repository Submission

Before pushing to GitHub:

1. Confirm `.env` is excluded from Git.
2. Review staged files for secrets and local artifacts.
3. Run the tests and record the actual result.
4. Verify Docker builds and starts successfully.
5. Update this README to reflect the real implementation.
6. Include setup instructions and test results that another developer can reproduce.

## License

Add a license if you intend to distribute this project under specific reuse terms.
