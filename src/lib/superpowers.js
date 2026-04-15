/**
 * superpowers.js
 *
 * Bundled skill content from github.com/obra/superpowers (MIT License).
 * Skills are appended to an agent's system prompt at run dispatch time
 * based on the `superpowersSkills` array stored in the agent config.
 */

const SKILLS = {
  'brainstorming': `## Skill: Brainstorming (Design-First Gate)
Do NOT write any code, scaffold any project, or take any implementation action until you have
presented a design and the user has explicitly approved it. There are no exceptions — even
"simple" tasks require a design approval step.

Steps:
1. Explore project context to understand the codebase
2. Ask clarifying questions one at a time (multiple-choice preferred)
3. Propose 2-3 approaches with trade-offs
4. Write a design doc to docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
5. Self-review the spec for completeness, consistency, clarity, scope, and YAGNI
6. Get explicit user approval on the design
7. Only then proceed to planning`,

  'writing-plans': `## Skill: Writing Plans
Break all work into 2-5 minute TDD-based tasks. Every task must contain exact file paths and
complete code — no placeholders, no "TBD", no vague instructions like "add validation".

Each task follows this exact sequence:
1. Write a failing test that demonstrates the desired behaviour
2. Run the test and verify it fails for the right reason
3. Write the simplest code to make the test pass
4. Run the test and verify it passes
5. Commit the change

Self-review checklist before presenting:
- Every spec requirement is covered by at least one task
- Zero placeholders or vague instructions
- Type names and function names are consistent across tasks`,

  'test-driven-development': `## Skill: Test-Driven Development
Non-negotiable: if you did not watch the test fail first, you do not know if it tests the
right thing. Writing tests after implementation defeats the purpose entirely.

RED-GREEN-REFACTOR cycle:
- RED: Write the minimal failing test that demonstrates the desired behaviour
- GREEN: Write the simplest code that makes that test pass — nothing more
- REFACTOR: Clean up while keeping all tests passing

Prohibited patterns:
- Writing any production code before a failing test exists
- Keeping "exploratory" code as reference — delete it and restart properly
- Mocking implementation details instead of testing actual behaviour
- Writing integration tests as an afterthought`,

  'executing-plans': `## Skill: Executing Plans
Before starting: load and review the full plan, raise any concerns, and confirm you understand
each task before proceeding.

During execution:
- Work through tasks in order; mark each complete before moving to the next
- Follow every step exactly as written — do not skip or reorder
- Stop immediately if you encounter: missing dependencies, unexplained test failures,
  unclear instructions, or repeated verification problems. Do not guess.

After all tasks: run the full test suite, verify everything passes, then use the
finishing-a-development-branch skill to wrap up.`,

  'verification-before-completion': `## Skill: Verification Before Completion
Never claim a task or feature is complete without fresh verification evidence obtained in this
session. "It should work" and "the tests were passing earlier" are not acceptable.

Process:
1. Identify the exact command that verifies the claim
2. Execute it completely — do not stop at the first success signal
3. Examine the full output and exit status
4. Confirm the output directly supports the completion claim
5. Only then state the result

Disqualified evidence: previous test runs, assumed fixes without retesting, partial checks,
agent-reported success without independent verification.`,

  'requesting-code-review': `## Skill: Requesting Code Review
After completing each task, dispatch a code-reviewer subagent before continuing. Provide:
- The full requirements list for the task
- The git SHA range that covers the changes (before..after)
- A brief description of what changed and why

Response protocol:
- Critical issues (broken behaviour, security, data loss): fix immediately before any other work
- Important issues (correctness, maintainability): fix before moving to the next task
- Minor issues (style, naming): note for later, do not block progress`,
};

export const SUPERPOWERS_SKILLS = [
  { id: 'brainstorming',                  label: 'Design-First Gate',   description: 'Block all coding until user approves a design doc' },
  { id: 'writing-plans',                  label: 'Structured Planning', description: 'Break work into 2-5 min TDD tasks with exact code' },
  { id: 'test-driven-development',        label: 'TDD Enforcement',     description: 'Mandatory RED-GREEN-REFACTOR, no code before tests' },
  { id: 'executing-plans',               label: 'Plan Execution',       description: 'Systematic task execution with stop-when-blocked rule' },
  { id: 'verification-before-completion', label: 'Evidence-Based Done', description: 'No completion claims without fresh verification output' },
  { id: 'requesting-code-review',         label: 'Auto Code Review',    description: 'Dispatch code-reviewer subagent after each task' },
];

/**
 * Compose skill markdown for the given skill IDs.
 * Returns an empty string if no skills are selected.
 * @param {string[]} skillIds
 * @returns {string}
 */
export function composeSuperpowersPrompt(skillIds) {
  if (!skillIds?.length) return '';
  const docs = skillIds.map((id) => SKILLS[id]).filter(Boolean);
  if (!docs.length) return '';
  return `\n\n---\n## Active Superpowers Skills\n\n${docs.join('\n\n')}`;
}
