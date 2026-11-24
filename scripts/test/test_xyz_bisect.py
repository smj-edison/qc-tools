import io
from pathlib import Path
from ase import Atoms
from ase.io.trajectory import Trajectory
import pytest

from xyz_bisect import BisectState, open_trajectory, run_bisect


def create_dummy_traj(path: Path, num_frames: int = 10) -> Path:
    """Create a sample ASE trajectory file with num_frames."""
    with Trajectory(str(path), mode="w") as t:
        for i in range(num_frames):
            # Frame i has two H atoms with distance 0.7 + i * 0.1
            dist = 0.7 + i * 0.1
            atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, dist]])
            t.write(atoms)
    return path


def test_open_trajectory(tmp_path):
    traj_path = create_dummy_traj(tmp_path / "test.traj", 5)
    traj = open_trajectory(traj_path)
    assert len(traj) == 5
    assert traj[0].get_chemical_symbols() == ["H", "H"]


def test_bisect_state_init_and_validation(tmp_path):
    traj_path = create_dummy_traj(tmp_path / "test.traj", 10)
    traj = open_trajectory(traj_path)

    # Valid init
    state = BisectState(traj, good_idx=0, bad_idx=9, output_dir=tmp_path)
    assert state.num_frames == 10
    assert state.good_idx == 0
    assert state.bad_idx == 9
    assert state.current_mid == 4  # (0 + 9) // 2

    # Invalid indices
    with pytest.raises(IndexError):
        BisectState(traj, good_idx=-1, bad_idx=9, output_dir=tmp_path)
    with pytest.raises(IndexError):
        BisectState(traj, good_idx=0, bad_idx=15, output_dir=tmp_path)


def test_bisect_workflow_step_files_and_current(tmp_path):
    # 7 frames (0, 1, 2, 3, 4, 5, 6)
    # Suppose frame 3 is the first bad frame
    traj_path = create_dummy_traj(tmp_path / "mol.traj", 7)
    traj = open_trajectory(traj_path)

    state = BisectState(traj, good_idx=0, bad_idx=6, output_dir=tmp_path)
    assert state.current_mid == 3  # (0 + 6) // 2

    # Write initial current.xyz
    current_path = state.write_current()
    assert current_path.exists()
    content = current_path.read_text()
    assert "Trajectory frame 3" in content

    # User marks frame 3 as bad
    archived_1, complete = state.record_verdict("bad")
    assert not complete
    assert archived_1 == tmp_path / "step-1-3.xyz"
    assert archived_1.exists()
    assert "Verdict: BAD" in archived_1.read_text()
    assert state.good_idx == 0
    assert state.bad_idx == 3
    assert state.step_num == 2
    assert state.current_mid == 1  # (0 + 3) // 2

    # Step 2: User marks frame 1 as good
    archived_2, complete = state.record_verdict("good")
    assert not complete
    assert archived_2 == tmp_path / "step-2-1.xyz"
    assert archived_2.exists()
    assert "Verdict: GOOD" in archived_2.read_text()
    assert state.good_idx == 1
    assert state.bad_idx == 3
    assert state.step_num == 3
    assert state.current_mid == 2  # (1 + 3) // 2

    # Step 3: User marks frame 2 as good -> bounds become good=2, bad=3 (adjacent) -> complete!
    archived_3, complete = state.record_verdict("good")
    assert complete
    assert archived_3 == tmp_path / "step-3-2.xyz"
    assert archived_3.exists()
    assert state.good_idx == 2
    assert state.bad_idx == 3
    assert state.is_complete()

    # Completion files should exist with frame index and hyphens
    first_bad_indexed = tmp_path / "first-bad-3.xyz"
    first_bad_generic = tmp_path / "first-bad.xyz"
    last_good_indexed = tmp_path / "last-good-2.xyz"
    last_good_generic = tmp_path / "last-good.xyz"

    assert first_bad_indexed.exists()
    assert first_bad_generic.exists()
    assert last_good_indexed.exists()
    assert last_good_generic.exists()
    assert "First bad structure" in first_bad_indexed.read_text()
    assert "3" in first_bad_indexed.read_text()
    assert "Last good structure" in last_good_indexed.read_text()
    assert "2" in last_good_indexed.read_text()


def test_bisect_undo(tmp_path):
    traj_path = create_dummy_traj(tmp_path / "mol.traj", 10)
    traj = open_trajectory(traj_path)

    state = BisectState(traj, good_idx=0, bad_idx=9, output_dir=tmp_path)
    state.write_current()
    assert state.current_mid == 4

    state.record_verdict("good")
    assert state.good_idx == 4
    assert state.step_num == 2
    assert state.current_mid == 6  # (4 + 9) // 2

    # Now undo
    undone = state.undo()
    assert undone is not None
    assert undone["step"] == 1
    assert undone["index"] == 4
    assert state.good_idx == 0
    assert state.bad_idx == 9
    assert state.step_num == 1
    assert state.current_mid == 4


def test_run_bisect_interactive_simulation(tmp_path):
    traj_path = create_dummy_traj(tmp_path / "sim.traj", 8)
    # 8 frames: 0..7
    # Midpoints:
    # Step 1: (0+7)//2 = 3. Say good -> good=3, bad=7
    # Step 2: (3+7)//2 = 5. Say bad  -> good=3, bad=5
    # Step 3: (3+5)//2 = 4. Say bad  -> good=3, bad=4 -> terminates!
    inputs = "good\nbad\nbad\n"
    stdin = io.StringIO(inputs)
    stdout = io.StringIO()

    exit_code = run_bisect(
        traj_path=traj_path,
        good_idx=0,
        bad_idx=7,
        output_dir=tmp_path,
        stdin=stdin,
        stdout=stdout,
    )

    assert exit_code == 0
    out = stdout.getvalue()
    assert "BISECT COMPLETE" in out
    assert "Last good structure: index 3" in out
    assert "First bad structure: index 4" in out
    assert (tmp_path / "step-1-3.xyz").exists()
    assert (tmp_path / "step-2-5.xyz").exists()
    assert (tmp_path / "step-3-4.xyz").exists()
    assert (tmp_path / "current.xyz").exists()
    assert (tmp_path / "first-bad-4.xyz").exists()
    assert (tmp_path / "first-bad.xyz").exists()
    assert (tmp_path / "last-good-3.xyz").exists()
    assert (tmp_path / "last-good.xyz").exists()


def test_run_bisect_with_view_command(tmp_path):
    traj_path = create_dummy_traj(tmp_path / "sim.traj", 8)
    # Test previewing index 0, then resetting view, then deciding
    inputs = "view 0\nview\ngood\nq\n"
    stdin = io.StringIO(inputs)
    stdout = io.StringIO()

    exit_code = run_bisect(
        traj_path=traj_path,
        output_dir=tmp_path,
        stdin=stdin,
        stdout=stdout,
    )
    # Ended with 'q'
    assert exit_code == 1
    out = stdout.getvalue()
    assert "Previewing structure 0" in out
    assert "Restored current bisect structure" in out


def test_cli_piped_interactive(run_script, tmp_path):
    import subprocess
    traj_path = create_dummy_traj(tmp_path / "cli_pipe.traj", 6)
    # Frames: 0, 1, 2, 3, 4, 5
    # Step 1: mid = 2. input: b -> good=0, bad=2
    # Step 2: mid = 1. input: b -> good=0, bad=1 -> completes!
    p = subprocess.run(
        [str(Path(__file__).parents[1] / "xyz_bisect"), str(traj_path), "-o", str(tmp_path)],
        cwd=tmp_path,
        input="b\nb\n",
        text=True,
        capture_output=True,
    )
    assert p.returncode == 0, p.stderr
    assert "BISECT COMPLETE" in p.stdout
    assert (tmp_path / "step-1-2.xyz").exists()
    assert (tmp_path / "step-2-1.xyz").exists()
    assert (tmp_path / "current.xyz").exists()
    assert (tmp_path / "first-bad-1.xyz").exists()
    assert (tmp_path / "first-bad.xyz").exists()
    assert (tmp_path / "last-good-0.xyz").exists()
    assert (tmp_path / "last-good.xyz").exists()


def test_large_trajectory_midpoint_naming(tmp_path):
    # Test that a 26003 frame trajectory produces step-1-13001.xyz
    class MockTraj:
        def __len__(self):
            return 26003

        def __getitem__(self, idx):
            return Atoms("H", positions=[[0, 0, 0]])

    traj = MockTraj()
    state = BisectState(traj, good_idx=0, bad_idx=26002, output_dir=tmp_path)
    assert state.calculate_mid() == 13001
    assert state.current_mid == 13001

    # When archiving step 1:
    fname, _ = state.record_verdict("bad")
    assert fname.name == "step-1-13001.xyz"
    assert fname.exists()


def test_no_archive_option(tmp_path):
    traj_path = create_dummy_traj(tmp_path / "mol.traj", 5)
    traj = open_trajectory(traj_path)
    state = BisectState(traj, good_idx=0, bad_idx=4, output_dir=tmp_path, archive_steps=False)
    archived, _ = state.record_verdict("good")
    assert archived is None
    assert not list(tmp_path.glob("step-*.xyz"))
    assert (tmp_path / "current.xyz").exists()


def test_cli_end_to_end(run_script, tmp_path):
    traj_path = create_dummy_traj(tmp_path / "cli.traj", 6)
    # Frames 0..5
    # Step 1: mid = 2. input: b -> good=0, bad=2
    # Step 2: mid = 1. input: b -> good=0, bad=1 -> complete!
    result = run_script(
        "xyz_bisect",
        str(traj_path),
        "-o",
        str(tmp_path),
        cwd=tmp_path,
    )
    # Since stdin was empty / EOF, it should exit cleanly with session ended
    assert "Loaded trajectory" in result.stdout
    assert "Session ended (EOF)" in result.stdout
