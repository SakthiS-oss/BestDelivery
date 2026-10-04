Use only the provided facts. Never mention a city, event, number, or headline that isn't in the input. Use hedged language ("elevated risk", "possible delay") and never claim a disruption will definitely happen.

Write one short explanation for each route id and one recommendation paragraph.
Return JSON only, with this shape:
{"routes": [{"id": "<route id from the input>", "explanation": "<plain English>"}], "recommendation": "<one paragraph>"}
Copy ids, city names, event names, headlines, and numbers from the input. Do not add a route.

Input:
