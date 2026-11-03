from locust import HttpUser, between, task


class EmployeeUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        r = self.client.post(
            "/auth/login",
            json={"phone_number": "هاتف-موظف", "password": "كلمة-سره", "pin": "رمزه"},
        )
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    @task
    def me(self):
        self.client.get("/auth/me", headers=self.headers)


    