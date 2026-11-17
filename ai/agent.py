
"""Google GenAI function-calling agent with user-scoped financial tools."""
import os
import json



SYSTEM_INSTRUCTION = """
You are FinSight, a user-controlled personal-finance assistant.

CORE PRINCIPLE:
Answer the user's specific question. The user decides which
financial topics they want to discuss. Never generate a complete
financial report unless explicitly requested.

CONTEXT AND TOOL USAGE RULES:

1. SPENDING AND INCOME:
   - Use get_my_financial_snapshot when the user asks about
     income, expenses, spending, or cash flow.
   - Include only the financial metrics relevant to the question.
   - Do not automatically include forecasts or savings goals.

2. SAVINGS GOALS:
   - Use get_my_savings_goals ONLY when the user explicitly asks
     about savings goals, goal progress, or goal-related planning.
   - Never mention existing savings goals just because they exist.
   - Do not assume the user wants to save for an existing goal.
   - Do not automatically include savings goals in spending analysis.

3. FORECASTING:
   - Include spending forecasts ONLY when the user asks for
     a forecast, prediction, or future spending estimate.
   - The financial snapshot may contain forecast data, but
     do not discuss it unless requested.

4. BUDGET RECOMMENDATIONS:
   - Use recommend_my_monthly_budget when the user asks
     to create or optimize a monthly budget.
   - Do not automatically include existing savings goals.
   - Include a savings reserve only when the user specifies
     an amount or explicitly asks for savings to be considered.
   - Never decide the user's savings target on their behalf.

5. GENERAL QUESTIONS:
   - Answer general financial questions without accessing
     personal financial data unless it is necessary.
   - Ask a clarifying question when the user's intent is unclear.

RESPONSE RULES:
6. Answer exactly what the user asks.
7. Do not add unrelated sections, forecasts, goals, or recommendations.
8. Keep answers concise and easy to understand.
9. Use the user's configured currency.
10. Never invent income, expenses, balances, forecasts, or savings progress.
11. Explain calculations when relevant.
12. Give practical, non-judgmental guidance.
13. Never claim to transfer money, create bank transactions,
    or change financial records.
14. If requested data is unavailable, explain what is missing.

The user is always in control of their financial planning decisions.
"""



def ask_financial_agent(user_id, question):
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Install the Google GenAI SDK using: pip install google-genai"
        ) from exc

    from ai.financial_tools import get_financial_snapshot, get_goal_plans
    from ai.budget_optimizer import recommend_budget

    # Each tool uses the authenticated user's ID from the Flask session.
    # The model cannot supply or override this ID.
    def get_my_financial_snapshot():
        return get_financial_snapshot(user_id)

    def get_my_savings_goals():
        return get_goal_plans(user_id)

    def recommend_my_monthly_budget(monthly_budget, savings_reserve=0.0):
        return recommend_budget(
            user_id,
            monthly_budget,
            savings_reserve
        )

    function_declarations = [
        types.FunctionDeclaration(
            name="get_my_financial_snapshot",
            description=(
                "Get the authenticated user's monthly income, spending, "
                "category-wise expenses and ML spending forecast."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        ),
        types.FunctionDeclaration(
            name="get_my_savings_goals",
            description=(
                "Get the authenticated user's active savings goals, "
                "progress and required daily or weekly savings."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        ),
        types.FunctionDeclaration(
            name="recommend_my_monthly_budget",
            description=(
                "Create a category-wise monthly budget using the user's "
                "historical ML spending predictions. Reserve savings first."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "monthly_budget": types.Schema(
                        type=types.Type.NUMBER,
                        description="Total monthly budget."
                    ),
                    "savings_reserve": types.Schema(
                        type=types.Type.NUMBER,
                        description="Amount to reserve for savings. Defaults to zero."
                    )
                },
                required=["monthly_budget"]
            )
        )
    ]

    available_tools = {
        "get_my_financial_snapshot": get_my_financial_snapshot,
        "get_my_savings_goals": get_my_savings_goals,
        "recommend_my_monthly_budget": recommend_my_monthly_budget,
    }

    client = genai.Client(api_key=api_key)

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=question)]
        )
    ]

    # Limit tool-calling rounds to prevent endless loops.
    for _ in range(5):
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                tools=[
                    types.Tool(
                        function_declarations=function_declarations
                    )
                ],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="AUTO"
                    )
                )
            )
        )

        if not response.candidates:
            return "I could not generate a response. Please try again."

        model_content = response.candidates[0].content
        contents.append(model_content)

        function_calls = [
            part.function_call
            for part in model_content.parts
            if part.function_call and part.function_call.name
        ]

        # No more tool calls: return Gemini's final answer.
        if not function_calls:
            answer_parts = [
                part.text
                for part in model_content.parts
                if part.text
            ]
            answer = "\n".join(answer_parts).strip()

            return answer or "I could not generate a response. Please try again."

        function_response_parts = []

        for function_call in function_calls:
            function_name = function_call.name
            function_args = dict(function_call.args or {})

            if function_name not in available_tools:
                result = {"error": "Unknown financial tool."}
            else:
                try:
                    result = available_tools[function_name](**function_args)
                    # Ensure the tool result contains JSON-compatible values.
                    result = json.loads(json.dumps(result, default=str))
                except Exception:
                    result = {
                        "error": "The requested financial calculation could not be completed."
                    }

            function_response_parts.append(
                types.Part.from_function_response(
                    name=function_name,
                    response={"result": result}
                )
            )

        contents.append(
            types.Content(
                role="user",
                parts=function_response_parts
            )
        )

    return (
        "I could not complete the financial analysis within the allowed "
        "number of tool calls. Please try a simpler question."
    )
