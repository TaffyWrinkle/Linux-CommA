# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
import logging
from datetime import datetime

import git

import Util.Config
from DatabaseDriver.DatabaseDriver import DatabaseDriver
from DatabaseDriver.SqlClasses import PatchData
from Util.Tracking import get_filenames


def should_keep_line(line: str):
    # Filter description by removing blank and unwanted lines
    ignore_phrases = (
        "reported-by:",
        "signed-off-by:",
        "reviewed-by:",
        "acked-by:",
        "cc:",
    )
    # TODO: Maybe just `return not line.lower().startswith(ignore_phrases)`?
    simplified_line = line.lower()
    if not simplified_line:
        return False
    if simplified_line.startswith(ignore_phrases):
        return False
    return True


def process_commits(
    repo: git.Repo,
    paths,
    revision="master",
    add_to_database=False,
    since=Util.Config.since,
) -> list:
    """
    Look at all commits in the given repo and handle based on distro.

    repo: Git.Repo object of the repository where we want to parse commits
    rev: revision we want to see the commits of, or None
    paths: list of filenames to check commits for
    add_to_database: whether or not to add to database (side-effect)
    since: if provided, will only process commits after this commit
    """
    all_patches = []
    num_patches = 0
    num_patches_added = 0

    # We use `--min-parents=1 --max-parents=1` to avoid both merges
    # and graft commits.
    commits = repo.iter_commits(
        rev=revision, paths=paths, min_parents=1, max_parents=1, since=since
    )

    logging.info("Starting commit processing...")
    for commit in commits:
        logging.debug(f"Parsing commit {commit.hexsha}")
        patch = PatchData(
            commitID=commit.hexsha,
            author=commit.author.name,
            authorEmail=commit.author.email,
            authorTime=datetime.utcfromtimestamp(commit.authored_date),
            commitTime=datetime.utcfromtimestamp(commit.committed_date),
        )
        # TODO abstract parsing description to another function to simplify and optimize
        # Especially with the checking of phrases starting in lines, we don't have to do separately.

        # Remove extra whitespace while splitting commit message
        split_message = [line.strip() for line in commit.message.split("\n")]
        patch.subject = split_message[0]

        description_lines = []
        # Check for blank description
        if len(split_message) > 1:
            description_lines = list(filter(should_keep_line, split_message[1:]))
            patch.description = "\n".join(description_lines)
        else:
            patch.description = ""

        # Check if this patch fixes other patches. This will fill
        # fixed_patches with a string of space-separated fixed patches
        # e.g. "SHA1 SHA2 SHA3"
        if patch.description != "":
            fixed_patches_lines = filter(
                lambda x: x.strip().lower().startswith("fixes:"),
                list(description_lines),
            )
            fixed_patches = []
            for line in fixed_patches_lines:
                words = line.split(" ")
                if len(words) > 1:
                    fixed_patches.append(words[1])
            patch.fixedPatches = " ".join(fixed_patches)

        patch.affectedFilenames = " ".join(get_filenames(commit))

        # Parse diff to only keep lines with changes (+ or - at start)
        # diff is passed in as bytes
        def parse_diff(diff):
            diff_lines = diff.decode("utf-8").splitlines()
            return "\n".join(
                filter(lambda line: line.startswith(("+", "-")), diff_lines)
            )

        if len(commit.parents) == 0:
            # First ever commit, we don't need to store this as
            # it'll be present in any distro as it's needed
            # TODO revisit, maybe check against set hash of first commit?
            # Get code some other way? Unsure if first commit matters or not.
            continue
        else:
            # We are ignoring merges so all commits should have a single parent
            commit_diffs = commit.tree.diff(
                commit.parents[0], paths=paths, create_patch=True
            )
        # The patch commit diffs are stored as "(filename1)\n(diff1)\n(filename2)\n(diff2)..."
        patch.commitDiffs = "\n".join(
            [
                "%s\n%s" % (diff.a_path, parse_diff(diff.diff))
                for diff in commit_diffs
                if diff.a_path is not None
            ]
        )

        if add_to_database:
            # TODO is this check needed if we start on only patches we haven't processed before?
            # If we DO want to keep this check, let's move before parsing everything
            with DatabaseDriver.get_session() as s:
                if (
                    s.query(PatchData.commitID)
                    .filter_by(commitID=patch.commitID)
                    .one_or_none()
                    is None
                ):
                    s.add(patch)
                    num_patches_added += 1
        else:
            all_patches.append(patch)

        num_patches += 1
        # Log progress
        if num_patches % 250 == 0:
            logging.debug(" %d commits processed..." % num_patches)

    if add_to_database:
        logging.info("%s patches added to database." % num_patches_added)
    return all_patches
