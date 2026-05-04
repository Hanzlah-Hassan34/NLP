"""
Locust Load Testing for DentaBot WebSocket API.

This replaces the custom throughput benchmark with Locust.

Run:
    locust -f evals/locustfile.py --host=ws://localhost:8000

Then open http://localhost:8089 in browser to configure and run tests.

Or headless:
    locust -f evals/locustfile.py --host=ws://localhost:8000 --headless -u 10 -r 2 -t 60s
"""
import json
import time
import uuid

from locust import User, task, between, events
import websocket


class DentaBotUser(User):
    """Simulates a user interacting with DentaBot via WebSocket."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    abstract = True  # Don't run this directly
    
    def on_start(self):
        """Called when a user starts."""
        self.session_id = f"locust_user_{uuid.uuid4().hex[:8]}"
        self.ws = None
        self._connect()
    
    def on_stop(self):
        """Called when a user stops."""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    def _connect(self):
        """Establish WebSocket connection."""
        start_time = time.time()
        try:
            ws_url = f"{self.host}/ws/chat"
            # Convert ws:// to proper format if needed
            if not ws_url.startswith("ws"):
                ws_url = f"ws://{self.host}/ws/chat"
            
            self.ws = websocket.create_connection(ws_url, timeout=60)
            
            # Reset session
            self.ws.send(json.dumps({
                "type": "reset",
                "session_id": self.session_id
            }))
            self.ws.recv()  # Wait for ack
            
            # Report successful connection
            events.request.fire(
                request_type="WebSocket",
                name="connect",
                response_time=(time.time() - start_time) * 1000,
                response_length=0
            )
            
        except Exception as e:
            events.request.fire(
                request_type="WebSocket",
                name="connect",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e
            )
    
    def _send_message(self, message: str, name: str, timeout: int = 60) -> dict:
        """Send a message and measure response time."""
        if not self.ws:
            self._connect()
            if not self.ws:
                return {"success": False, "error": "No connection"}
        
        start_time = time.time()
        first_token_time = None
        tokens = []
        
        try:
            # Send chat message
            self.ws.send(json.dumps({
                "type": "chat",
                "session_id": self.session_id,
                "message": message,
                "stream": True
            }))
            
            # Collect response
            while True:
                response = self.ws.recv()
                recv_time = time.time()
                
                data = json.loads(response)
                event_type = data.get("type")
                
                if event_type == "token":
                    if first_token_time is None:
                        first_token_time = recv_time
                    tokens.append(data.get("data", {}).get("token", ""))
                elif event_type == "complete":
                    break
                elif event_type == "error":
                    raise Exception(data.get("data", {}).get("message", "Unknown error"))
            
            end_time = time.time()
            total_time = (end_time - start_time) * 1000  # ms
            ttft = (first_token_time - start_time) * 1000 if first_token_time else total_time
            
            # Report success
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=len("".join(tokens))
            )
            
            # Also report TTFT as separate metric
            events.request.fire(
                request_type="TTFT",
                name=f"{name}_ttft",
                response_time=ttft,
                response_length=0
            )
            
            return {
                "success": True,
                "total_ms": total_time,
                "ttft_ms": ttft,
                "tokens": len(tokens)
            }
            
        except Exception as e:
            total_time = (time.time() - start_time) * 1000
            events.request.fire(
                request_type="WebSocket",
                name=name,
                response_time=total_time,
                response_length=0,
                exception=e
            )
            
            # Try to reconnect
            self._connect()
            
            return {"success": False, "error": str(e)}
    
    @task(3)
    def simple_greeting(self):
        """Simple greeting - most common task."""
        self._send_message("Hello", "simple_greeting")
    
    @task(2)
    def faq_question(self):
        """FAQ question requiring RAG."""
        questions = [
            "What are your opening hours?",
            "Do you accept insurance?",
            "Where is the clinic located?",
        ]
        import random
        self._send_message(random.choice(questions), "faq_question")
    
    @task(2)
    def cost_inquiry(self):
        """Cost inquiry requiring tool call."""
        procedures = ["checkup", "cleaning", "whitening", "braces"]
        import random
        self._send_message(
            f"How much does {random.choice(procedures)} cost?",
            "cost_inquiry"
        )
    
    @task(1)
    def booking_flow(self):
        """Multi-turn booking conversation."""
        self._send_message("I want to book an appointment", "booking_start")


# Concrete user class for running tests
class DentaBotWebSocketUser(DentaBotUser):
    """Concrete user class for WebSocket load testing."""
    abstract = False


# HTTP-based user for faster testing (no LLM wait)
from locust import HttpUser

class DentaBotHttpUser(HttpUser):
    """HTTP-based user for testing API endpoints (faster)."""
    
    wait_time = between(0.5, 1)
    
    @task(5)
    def health_check(self):
        """Quick health check endpoint."""
        self.client.get("/")
    
    @task(1)
    def static_page(self):
        """Load static HTML page."""
        self.client.get("/")


# Event hooks for custom reporting
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary when test stops."""
    print("\n" + "="*60)
    print("LOCUST LOAD TEST COMPLETE")
    print("="*60)
    
    stats = environment.stats
    print(f"\nTotal Requests: {stats.total.num_requests}")
    print(f"Failures: {stats.total.num_failures}")
    print(f"Median Response Time: {stats.total.median_response_time}ms")
    print(f"Average Response Time: {stats.total.avg_response_time:.0f}ms")
    print(f"Max Response Time: {stats.total.max_response_time}ms")
    print(f"Requests/sec: {stats.total.total_rps:.2f}")
