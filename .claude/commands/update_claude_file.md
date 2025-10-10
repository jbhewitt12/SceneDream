# Update CLAUDE.md - Claude Code Command

This command systematically updates CLAUDE.md with the latest codebase information while maintaining conciseness and relevance.

## Execution Steps

### 1. Analyze Current Codebase Structure
First, examine the repository to identify all major systems and components:

- **Backend Services**: Search for new services in `backend/app/services/`
- **API Routes**: Check `backend/app/api/routes/` for new endpoints
- **Database Models**: Review `backend/app/models.py` for schema changes
- **Scripts**: Scan `scripts/` directory for new utility scripts
- **Configuration**: Check for new environment variables or config files
- **Docker Services**: Review `docker-compose.yml` for new services

### 2. Identify Critical Updates
Look for these specific items that should be in CLAUDE.md:

#### New Systems/Features
- Trading strategies or algorithms
- Integration with new APIs
- Authentication/authorization changes
- New background tasks or scheduled jobs
- WebSocket connections or real-time features

#### Development Workflow Changes
- New development commands
- Updated testing procedures
- Changed deployment processes
- New linting/formatting tools
- Package management updates

#### Architecture Evolution
- Service dependencies
- Data flow changes
- New design patterns
- Performance optimizations
- Security enhancements

### 3. Update Guidelines

#### What to Include ✅
- **Essential Commands**: Commands developers use daily
- **Non-Obvious Patterns**: Project-specific conventions that differ from defaults
- **Integration Points**: How systems connect and communicate
- **Critical Files**: Key files that developers frequently need to modify
- **Common Pitfalls**: Known issues and their solutions
- **Active Features**: Only document features actually in use

#### What to Exclude ❌
- **Standard Framework Features**: Don't explain FastAPI basics
- **Unused Code**: Remove references to deprecated/unused features
- **Verbose Explanations**: Keep descriptions to 1-2 sentences
- **Implementation Details**: Focus on "what" not "how"
- **Temporary Workarounds**: Only include permanent solutions
- **Generated Files**: Don't document auto-generated content

### 4. Format and Structure

#### Optimal Section Order
1. **Project Overview** (3-5 sentences max)
2. **Common Development Commands** (grouped by task)
3. **Core Architecture** (visual diagram if helpful)
4. **Key Components** (bullet points with file paths)
5. **Technology Stack** (concise list)
6. **Development Notes** (only critical information)

#### Writing Style
- Use bullet points over paragraphs
- Include file paths for quick navigation
- Group related commands together
- Use code blocks for multi-line commands
- Add brief comments only when necessary

### 5. Validation Checklist

Before finalizing updates, ensure:
- [ ] Total file size remains under 3KB (ideal)
- [ ] No duplicate information
- [ ] All commands are tested and working
- [ ] File paths are accurate
- [ ] No implementation details, only interface descriptions
- [ ] Focus on developer experience

### 6. Example Update Process

```bash
# 1. Search for new services
find backend/app/services -name "*.py" -newer CLAUDE.md

# 2. Check for new API routes
grep -r "router = APIRouter" backend/app/api/routes/

# 3. Look for new scripts
ls -la scripts/*.py

# 4. Review recent commits for major changes
git log --oneline --since="1 month ago" -- backend/

# 5. Check for new dependencies
diff backend/pyproject.toml <previous-version>
```

### 7. Sample CLAUDE.md Section Updates

#### Adding a New Service
```markdown
- `app/services/new_service/`: Brief description of what it does
  - `processor.py`: Main processing logic
  - `models.py`: Service-specific data models
```

#### Adding a New Command
```markdown
- **Run new task**: `python -m app.tasks.new_task` (brief description)
```

#### Updating Architecture
```markdown
### Core Architecture
```
Twitter → WebSocket → LLM → Decision → Polymarket → Execution
                      ↓
                  Database
```
```

### 8. Final Review Questions

Ask yourself:
- Would a new developer understand the project after reading this?
- Can they start developing without asking basic questions?
- Is every piece of information actionable?
- Could anything be removed without losing value?

## Command Execution

To update CLAUDE.md:
1. Run through steps 1-7 above
2. Create a backup: `cp CLAUDE.md CLAUDE.md.backup`
3. Make updates incrementally
4. Test all documented commands
5. Commit with message: "Update CLAUDE.md with latest project structure"

Remember: CLAUDE.md is a living document that should evolve with the project, but resist the urge to over-document. When in doubt, leave it out.