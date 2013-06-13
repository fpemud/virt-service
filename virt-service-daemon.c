#include <sys/types.h>
#include <unistd.h>
#include <pwd.h>
#include <grp.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[])
{
	char **args;
	struct passwd *pw;
	struct group *gr;
	int i;

	pw = getpwuid(getuid());
	if (!pw)
	{
		fputs("Error: Could not get passwd entry.\n", stderr);
		exit(1);
	}

	gr = getgrgid(getgid());
	if (!gr)
	{
		fputs("Error: Could not get group entry.\n", stderr);
		exit(1);
	}

	/* malloc args */
	args = malloc((7 + argc) * sizeof(char*));	// Yeah, I know, no free()
	if (!args)					// well, exec() and exit() free anyway!
	{
		fputs("Error: Out of memory.\n", stderr);
		exit(1);
	}

	/* args[0]: python executable */
	args[0] = "/usr/bin/python2";

	/* args[1]: main python file */
	args[1] = "/usr/libexec/virt-service/virt-service.py";

	/* args[2]: userid */
	args[2] = malloc(64);
	if (!args[2])
	{
		fputs("Error: Out of memory.\n", stderr);
		exit(1);
	}
	snprintf(args[2], 64, "%d", pw->pw_uid);

	/* args[3]: username */
	args[3] = pw->pw_name;

	/* args[4]: groupid */
	args[4] = malloc(64);
	if (!args[4])
	{
		fputs("Error: Out of memory.\n", stderr);
		exit(1);
	}
	snprintf(args[4], 64, "%d", gr->gr_gid);

	/* args[5]: groupname */
	args[5] = gr->gr_name;

	/* args[6]: workdir */
	args[6] = getcwd(NULL, 0);

	/* other arguments */
	for (i = 1; i < argc; i++)
	{
		args[6 + i] = argv[i];
	}
	args[6 + i] = NULL;

	/* rise the priviledge and execute main.py */
	if (setuid(geteuid()))
	{
		fputs("Error: Rise priviledge failed.\n", stderr);
		exit(1);
	}
	execvp(args[0], args);

	exit(1);				// should not reach
}


