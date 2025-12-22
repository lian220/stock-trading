# Prompt Generation Guide

This guide outlines the standard process for creating high-quality, effective prompts. Use this guide when asked to "generate a prompt" or when you need to construct a prompt for another AI agent.

## Core Components of an Effective Prompt

A robust prompt typically contains the following elements. Not all are strictly necessary for every simple task, but complex tasks require them for reliability.

1.  **Role (Persona)**: Who is the AI acting as? (e.g., "You are a Senior Python Backend Engineer")
2.  **Context**: Background information necessary to understand the task. (e.g., "We are building a stock trading bot using FastAPI...")
3.  **Task (Instruction)**: The specific action the AI needs to perform. Be active and direct. (e.g., "Create a function to calculate RSI...")
4.  **Constraints**: What the AI must NOT do, or limits it must work within. (e.g., "Do not use external libraries other than Pandas...")
5.  **Output Format**: How the result should look. (e.g., "Return a JSON object," "Provide a Markdown table," "Only output code")
6.  **Examples (Few-Shot)**: Optional but powerful. Show, don't just tell.

## Step-by-Step Generation Process

1.  **Analyze the Request**: specific goal, key requirements.
2.  **Define the Persona**: Select the most appropriate expert role.
3.  **Draft the Instruction**: Write clear, active-voice commands.
4.  **Add Context & Constraints**: Refine boundaries to prevent hallucinations or wrong formats.
5.  **Specify Output**: clearly define what the "done" state looks like.
6.  **Review**: Read the prompt to ensure it is unambiguous.

## Prompt Template

```markdown
# Role
You are a [Expert Role, e.g., Senior Data Scientist].

# Context
[Provide background context, e.g., Working on a time-series forecasting model for stock prices using LSTM.]

# Task
[Specific instructions, e.g., Analyze the provided dataset and identify missing values. Propose 3 methods for imputation.]

# Constraints
- [Constraint 1, e.g., Do not remove rows.]
- [Constraint 2, e.g., Use Python 3.10+ syntax.]

# Output Format
[Desired format, e.g., A Python script with comments explaining each step.]
```

## Examples

### ❌ Bad Prompt
> "Write code for stock stuff."
> *Why it fails: Too vague, no context, no constraints.*

### ✅ Good Prompt
> **Role**: Senior Python Developer
> **Context**: We are building a trading bot. We have a list of OHLCV data.
> **Task**: Write a Python function `calculate_moving_average` that takes a list of prices and a window size, and returns the simple moving average.
> **Constraints**: Use only standard libraries if possible, or `numpy`. Handle empty lists gracefully.
> **Output**: Valid Python code block only.

## Usage for AI Assistant

If the user asks you to "generate a prompt" for a specific task:
1.  Ask clarifying questions if the goal is vague.
2.  Use the Template above to structure the prompt.
3.  Fill in the sections based on the user's request.
4.  Present the result in a code block for easy copying.
