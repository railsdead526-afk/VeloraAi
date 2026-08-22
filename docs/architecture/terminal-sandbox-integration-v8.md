# Terminal Sandbox Integration v1

Terminal tools use the versioned SandboxClient boundary. An execution without a workspace ID gets an ephemeral workspace that is deleted after execution. An explicit workspace ID may be reused for multi-step workflows and must be authorized by the orchestration layer against the authenticated user, conversation, and session.