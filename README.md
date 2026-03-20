---
title: RAWV
emoji: "🔬"
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

## Rawv

[text](https://huggingface.co/spaces/Shreemahor/Rawv)

***Research AI With Voice***

## Features

1. Responds Back in Voice
2. Rawv can understand your speech
3. Deep, Transparent Research

## Research Flow

transcribe -> search -> browse -> synthesize -> quality check -> speak
*The summary is what is spoken*

1. Concise answer
A quick paragraph answer to the research question.
2. Bullet Points
Main takeaways and what was found in research - usually 7
3. Contradictions/Gaps
Important part of research to know what is still not confirmed yet
4. Summary
what is spoken and for the 'tl;dr' people
5. Sources
must always stay transparent and can go back to source to check
The steps taken like tools, browse, and synthesize are displayed

## Tech Stack

All Python
**Langchain & Langgraph** - Python libararies for using gen AI
**RAWV Web UI** - Voice-first interface for chat, controls, and transparent research steps
**Chrome MCP Server** - To connect to chrome to do research
**DuckDuckGo** - Free search

## Models

Speech (TTS) - *en-US-AriaNeural*
Audio Input (STT) - *whisper-large-v3-turbo*
Brain (Core) - *llama-3.1-8b-instant*

## AI Usage

I made the base backend but then I ran into very tricky audio errors when trying to get a response back, so I got help from copilot.

## Future

I could look at more websites, and I could get it to write a long research-report too. Another idea is to connect it to Alexa so I can always activate it.
