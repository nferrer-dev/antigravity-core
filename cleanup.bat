@echo off
git stash
set FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --force --index-filter "git rm --cached --ignore-unmatch .agents/sidecars/antigravity_phone_chat/0001-isolated-patch.patch .agents/sidecars/antigravity_phone_chat/diff.patch .agents/sidecars/antigravity_phone_chat/diff2.patch temp_patch.diff" --prune-empty --tag-name-filter cat -- --all
git stash pop
