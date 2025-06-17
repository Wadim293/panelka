# redis_client.py
import redis.asyncio as redis

redis_client = redis.from_url(
    "rediss://default:AYFVAAIjcDE2MWYzZWFlNGJiMDI0OGU3OWFiYTMxMzAwOTA3NjA2NHAxMA@guiding-polecat-33109.upstash.io:6379",
    decode_responses=True
)