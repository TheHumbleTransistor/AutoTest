import subprocess
import os

# Returns the commit SHA of a git repository
def commitSha(dir=os.path.dirname(os.path.realpath(__file__)), short=True):
	gitFile = dir + "/.git"
	try:
		sha = subprocess.check_output(["git", "--git-dir", gitFile ,"log", "-1", "--format=\"%H\""]).replace('"', '').rstrip()
	except:
		return None
	if len(sha) is not 40:
		return None
	return sha[0:6] if short else sha

if __name__ == '__main__':
	print commitSha()
