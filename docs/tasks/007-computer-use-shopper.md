# Task 007 — Run the five shopper stories with a computer-use agent

**Status** · Planned.

Use the same generated storefront and grading criteria as the [scripted runner](006-scripted-browser-tests.md). The shopper receives the request and interacts with the site through browser screenshots, clicks, scrolling, and typing. The harness holds the expected answers and observes the mock checkout.

## Running and grading

Provide one local command that accepts the generated site directory, its source feed, and the shopper model. Reuse Task 6’s serving and grading code so both runners evaluate the same build. Record the build identity, model, and attempt limits with the results.

For a lookup, the shopper returns the requested facts as its final answer. Grade those facts using Task 6’s formatting rules and check for zero submissions. For checkout, check the mock’s accepted order and the confirmation visible in the browser. For the edit story, the first instruction ends with “Show me my cart.” When the shopper signals it is ready, verify one tea and one rice in the visible cart before releasing the second instruction.

## Pass@3 per story

1. Start each attempt on the homepage with an empty cart, a fresh agent conversation, and a separate record of mock order activity. Use the same build, shopper request, model settings, and step limit across attempts.
2. Grade the whole attempt against the [agreed story outcome](../website-feature-roadmap.md#agreed-thai-peacock-shopper-stories). For the edit story, give the change request only after the initial cart is verified. Both stages must succeed in the same attempt.
3. Stop trying that story as soon as it passes. After three unsuccessful attempts, mark it failed. Continue until all five stories have a result.
4. Report how many stories passed out of five and the result of each attempt taken. Keep the action history and screenshot for each failure, including failures followed by a successful retry.

The suite passes when all five stories pass within their individual three-attempt limits. A full run takes between five and fifteen attempts.

A wrong answer, wrong order, or exhausted shopper step budget uses an attempt. If the browser, model service, or mock is unavailable and grading cannot finish, stop the run and report it as incomplete. Keep completed results. Choose and document a default step limit during the first live run, then hold it fixed for comparisons.

## Done when

- A teammate can run all five stories against the Task 6 build and find the per-attempt results, failure reasons, and evidence. The command signals success only for a 5/5 pass.
- A repeatable test of the retry logic demonstrates a first-attempt pass, a pass on the second attempt, and three failures. Check that early stopping skips only the remaining attempts for that story and that a retry inherits no cart, conversation, or order events.
- Run the real computer-use shopper on the template-generated Thai Peacock site and record the baseline, including the model identifier, how many stories passed on their first attempt, and how many passed within three.
