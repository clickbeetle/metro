
"""
This class does all of the chroot setup, copying of files, etc. It is
the driver class for pretty much everything that Catalyst does.
"""

import os,string,imp,types,shutil
from catalyst_support import *
from generic_target import *
from stat import *

class generic_stage_target(generic_target):

	def __init__(self,settings):
		
		generic_target.__init__(self,settings)

		for x in os.listdir(settings["sharedir"]+"/arch"):
			if x.endswith(".spec"):
				self.settings.collect(settings["sharedir"]+"/arch/"+x)
		
		# If subarch is specified as "~pentium4", set the realsubarch to "pentium4". This info will be
		# used when validating the subarch so a user-specified "~pentium4" will be interpreted as valid.

		# We also use an initial "~" as a trigger to build an unstable version of the portage tree. This
		# means we need to use ~arch rather than arch in ACCEPT_KEYWORDS. So if someone specified "~pentium4"
		# as subarch, we would set ACCEPT_KEYWORDS to "~x86" and later write this into make.conf.
		
		if self.settings["subarch"][0] == "~":
			self.settings["realsubarch"] = self.settings["subarch"][1:]
			self.settings["ACCEPT_KEYWORDS"] = "~"+self.settings["arch"]
		else:
			self.settings["realsubarch"] = self.settings["subarch"]
			self.settings["ACCEPT_KEYWORDS"] = self.settings["arch"]

		# All the ~x86, ~pentium4, etc. unstable subarch build logic should be done now. Now we need to make
		# sure that we use the new variables for paths, below...
		
		self.require(["target","subarch","rel_type","profile","snapshot","source_subpath"])

#"""
#target_subpath: $[rel_type]/$[target]-$[subarch]-$[version_stamp]
#snapshot_path: $[storedir]/snapshots/$[portname]-$[snapshot].tar.bz2
#root_path: /
#source_path: $[storedir]/builds/$[source_subpath].tar.bz2
#chroot_path: $[storedir]/tmp/$[target_subpath]/
#destpath: $[chroot_path]/$[root_path]
#stage_path: $[chroot_path]
#target_path: $[storedir]/builds/$[target_subpath].tar.bz2
#controller_file: $[sharedir]/targets/$[target]/$[target]-controller.sh
#action_sequence: unpack unpack_snapshot config_profile_link setup_confdir portage_overlay base_dirs bind chroot_setup setup_environment run_local preclean unbind clean
#cleanables: /etc/resolv.conf /var/tmp/* /tmp/* /root/* /usr/portage
#USE: $[HOSTUSE]

#NOW THE flexdata should be pretty much all defined.... whee ha.
#"""

	def run(self):
		# STUFF WE NEED
		file_locate(self.settings,["source_path","snapshot_path","distdir"],expand=0)

		# setup our mount points

		self.mounts=[ "/proc","/dev","/usr/portage/distfiles", "/dev/pts" ]
		self.mountmap={"/proc":"/proc", "/dev":"/dev", "/dev/pts":"/dev/pts",\
				"/usr/portage/distfiles":self.settings["distdir"]}
		self.set_mounts()

		if self.settings.has_key("CCACHE"):
			if os.environ.has_key("CCACHE_DIR"):
				ccdir=os.environ["CCACHE_DIR"]
				del os.environ["CCACHE_DIR"]
			else:
				ccdir="/root/.ccache"
			if not os.path.isdir(ccdir):
					raise CatalystError,\
						"Compiler cache support can't be enabled (can't find "+ccdir+")"
			self.mounts.append("/var/tmp/ccache")
			self.mountmap["/var/tmp/ccache"]=ccdir
			# for the chroot:
			self.env["CCACHE_DIR"]="/var/tmp/ccache"	
		# Kill any pids in the chroot
		self.kill_chroot_pids()

		# Check for mounts right away and abort if we cannot unmount them.
		self.mount_safety_check()

		# BEFORE WE START
		self.purge()

		for x in self.settings["action_sequence"]:
			print "--- Running action sequence: "+x
			sys.stdout.flush()
			try:
				apply(getattr(self,x))
			except:
				self.mount_safety_check()
				raise
			# first clean up any existing target stuff
	def kill_chroot_pids(self):
	    print "Checking for processes running in chroot and killing them."
	    
	    # Force environment variables to be exported so script can see them
	    self.setup_environment()

	    if os.path.exists(self.settings["sharedir"]+"/targets/support/kill-chroot-pids.sh"):
			    cmd("/bin/bash "+self.settings["sharedir"]+"/targets/support/kill-chroot-pids.sh",\
			    			"kill-chroot-pids script failed.",env=self.env)
	
	def mount_safety_check(self):
		mypath=self.settings["chroot_path"]
		
		"""
		check and verify that none of our paths in mypath are mounted. We don't want to clean
		up with things still mounted, and this allows us to check. 
		returns 1 on ok, 0 on "something is still mounted" case.
		"""
		if not os.path.exists(mypath):
			return
		
		for x in self.mounts:
			if not os.path.exists(mypath+x):
				continue
			
			if ismount(mypath+x):
				#something is still mounted
				try:
					print x+" is still mounted; performing auto-bind-umount...",
					# try to umount stuff ourselves
					self.unbind()
					if ismount(mypath+x):
						raise CatalystError, "Auto-unbind failed for "+x
					
					else:
						print "Auto-unbind successful..."
				
				except CatalystError:
					raise CatalystError, "Unable to auto-unbind "+x
		
	def unpack(self):
		unpack=True

		if True:	
			display_msg="\nStarting tar extract from "+self.settings["source_path"]+"\nto "+\
				self.settings["chroot_path"]+" (This may take some time) ...\n"
			unpack_cmd="tar xjpf "+self.settings["source_path"]+" -C "+self.settings["chroot_path"]
			error_msg="Tarball extraction of "+self.settings["source_path"]+" to "+self.settings["chroot_path"]+" failed."
		
		invalid_snapshot=False

		if unpack:
			self.mount_safety_check()
			
			if not os.path.exists(self.settings["chroot_path"]):
				os.makedirs(self.settings["chroot_path"])

			if not os.path.exists(self.settings["chroot_path"]+"/tmp"):
				os.makedirs(self.settings["chroot_path"]+"/tmp",1777)
			
			if self.settings.has_key("PKGCACHE"):	
				if not os.path.exists(self.settings["pkgcache_path"]):
					os.makedirs(self.settings["pkgcache_path"],0755)
			
			if self.settings.has_key("KERNCACHE"):	
				if not os.path.exists(self.settings["kerncache_path"]):
					os.makedirs(self.settings["kerncache_path"],0755)
			
			print display_msg
			cmd(unpack_cmd,error_msg,env=self.env)

		else:
		    print "Resume point detected, skipping unpack operation..."
	

	def unpack_snapshot(self):
		destdir=normpath(self.settings["chroot_path"]+"/usr/portage")
		cleanup_errmsg="Error removing existing snapshot directory."
		cleanup_msg="Cleaning up existing portage tree (This can take a long time) ..."
		unpack_cmd="tar xjpf "+self.settings["snapshot_path"]+" -C "+self.settings["chroot_path"]+"/usr"
		unpack_errmsg="Error unpacking snapshot"
	
		if os.path.exists(destdir):
			print cleanup_msg
			cleanup_cmd="rm -rf "+destdir
			cmd(cleanup_cmd,cleanup_errmsg,env=self.env)
		if not os.path.exists(destdir):
			os.makedirs(destdir,0755)
		    	
		print "Unpacking \""+self.settings["portname"]+"\" portage tree "+self.settings["snapshot_path"]+" ..."
		cmd(unpack_cmd,unpack_errmsg,env=self.env)

	def config_profile_link(self):
		print "Configuring profile link..."
		cmd("rm -f "+self.settings["chroot_path"]+"/etc/make.profile",\
				"Error zapping profile link",env=self.env)
		cmd("ln -sf ../usr/portage/profiles/"+self.settings["profile"]+" "+self.settings["chroot_path"]+"/etc/make.profile","Error creating profile link",env=self.env)
				       
	def setup_confdir(self):	
		if self.settings.has_key("portage_confdir"):
			print "Configuring /etc/portage..."
			cmd("rm -rf "+self.settings["chroot_path"]+"/etc/portage","Error zapping /etc/portage",env=self.env)
			cmd("cp -R "+self.settings["portage_confdir"]+"/ "+self.settings["chroot_path"]+\
				"/etc/portage","Error copying /etc/portage",env=self.env)
	
	def bind(self):
		for x in self.mounts: 
			if not os.path.exists(self.settings["chroot_path"]+x):
				os.makedirs(self.settings["chroot_path"]+x,0755)
			
			if not os.path.exists(self.mountmap[x]):
				os.makedirs(self.mountmap[x],0755)
			
			src=self.mountmap[x]
			if os.uname()[0] == "FreeBSD":
				if src == "/dev":
					retval=os.system("mount -t devfs none "+self.settings["chroot_path"]+x)
				else:
					retval=os.system("mount_nullfs "+src+" "+self.settings["chroot_path"]+x)
			else:
				retval=os.system("mount --bind "+src+" "+self.settings["chroot_path"]+x)
			if retval!=0:
				self.unbind()
				raise CatalystError,"Couldn't bind mount "+src
			    
	
	def unbind(self):
		ouch=0
		mypath=self.settings["chroot_path"]
		myrevmounts=self.mounts[:]
		myrevmounts.reverse()
		# unmount in reverse order for nested bind-mounts
		for x in myrevmounts:
			if not os.path.exists(mypath+x):
				continue
			
			if not ismount(mypath+x):
				# it's not mounted, continue
				continue
			
			retval=os.system("umount "+os.path.join(mypath,x.lstrip(os.path.sep)))
			
			if retval!=0:
				warn("First attempt to unmount: "+mypath+x+" failed.")
				warn("Killing any pids still running in the chroot")
				
				self.kill_chroot_pids()
				
				retval2=os.system("umount "+mypath+x)
				if retval2!=0:
				    ouch=1
				    warn("Couldn't umount bind mount: "+mypath+x)
				    # keep trying to umount the others, to minimize damage if developer makes a mistake
		if ouch:
			"""
			if any bind mounts really failed, then we need to raise
			this to potentially prevent an upcoming bash stage cleanup script
			from wiping our bind mounts.
			"""
			raise CatalystError,"Couldn't umount one or more bind-mounts; aborting for safety."

	def chroot_setup(self):

		# SETUP PROXY SETTINGS - ENVSCRIPT DOESN'T ALWAYS WORK. THIS DOES.
		
		print "Writing out proxy settings... (drobbins)"
		try:
			a=open(self.settings["chroot_path"]+"/etc/env.d/99zzcatalyst","w")
		except:
			raise CatalystError,"Couldn't open "+self.settings["chroot_path"]+"/etc/env.d/99zzcatalyst for writing"
		for x in ["http_proxy","ftp_proxy","RSYNC_PROXY"]:
			if os.environ.has_key(x):
				a.write(x+"=\""+os.environ[x]+"\"\n")
			else:
				a.write("# "+x+" is not set")
		a.close()

		# SETUP LOCALES SPECIFIED IN SPEC FILE (IF ANY - DEFAULT TO ALL)

		if self.settings.has_key("locales"):
			# our locale.gen template (nothing in it except comments: )
			srcfile=self.settings["sharedir"]+"/misc/locale.gen"
			# our destination locale.gen file:
			locfile=self.settings["chroot_path"]+"/etc/locale.gen"
			cmd("rm -f "+locfile)
			cmd("install -m0644 -o root -g root "+srcfile+" "+locfile)
			try:
				#open to append locale entries
				a=open(locfile,"a")
			except:
				raise CatalystError,"Couldn't open "+locfile+" for writing."
			for localepair in self.settings["locales"]:
				locale,charmap = localepair.split("/")
				a.write(locale+" "+charmap+"\n")
			#all done writing out our locales/charmaps
			a.close()

		print "Setting up chroot..."
	
		# COPY OVER /etc/resolv.conf

		cmd("cp /etc/resolv.conf "+self.settings["chroot_path"]+"/etc","Could not copy resolv.conf into place.",env=self.env)
	
		# COPY OVER ENVSCRIPT
		
		if self.settings.has_key("ENVSCRIPT"):
			if not os.path.exists(self.settings["ENVSCRIPT"]):
				raise CatalystError, "Can't find envscript "+self.settings["ENVSCRIPT"]
			
			cmd("cp "+self.settings["ENVSCRIPT"]+" "+self.settings["chroot_path"]+"/tmp/envscript","Could not copy envscript into place.",env=self.env)
		
		# BACK UP ORIGINAL /etc/hosts, COPY WORKING /etc/hosts SO WE CAN FUNCTION BETTER, WILL RESTORE LATER

		if os.path.exists(self.settings["chroot_path"]+"/etc/hosts"):
			cmd("mv "+self.settings["chroot_path"]+"/etc/hosts "+self.settings["chroot_path"]+"/etc/hosts.bck", "Could not backup /etc/hosts",env=self.env)
			cmd("cp /etc/hosts "+self.settings["chroot_path"]+"/etc/hosts", "Could not copy /etc/hosts",env=self.env)
		
		# SET UP MAKE.CONF
		
		cmd("rm -f "+self.settings["chroot_path"]+"/etc/make.conf","Could not remove "+self.settings["chroot_path"]+"/etc/make.conf",env=self.env)
		
		myf=open(self.settings["chroot_path"]+"/etc/make.conf","w")

		myf.write("# These settings were set by the catalyst build script that automatically\n# built this stage.\n")
		myf.write("# Please consult /etc/make.conf.example for a more detailed example.\n")

		for opt in ["CFLAGS","CXXFLAGS","LDFLAGS","CBUILD","CHOST","ACCEPT_KEYWORDS","USE"]:
			if self.settings.has_key(opt):
				myf.write(opt+'="'+self.settings[opt]+'"\n')

		# SET UP USE VARS
		
		myusevars=[]
		if self.settings.has_key("HOSTUSE"):
			myusevars.extend(self.settings["HOSTUSE"])
	
		if self.settings.has_key("use"):
			myusevars.extend(self.settings["use"])
			myf.write('USE="'+string.join(myusevars)+'"\n')

		myf.close()
	
	def clean(self):
		# drobbins add
	    	if self.settings["destpath"] == self.settings["chroot_path"]:
		# clean up possibly sensitive proxy settings that we set up in the chroot
			for x in ["/etc/profile.env","/etc/csh.env","/etc/env.d/99zzcatalyst"]:
				if os.path.exists(self.settings["chroot_path"]+x):
					print "Cleaning chroot: "+x+"... " 
					cmd("rm -f "+self.settings["chroot_path"]+x)
		# drobbins add end
		for x in self.settings["cleanables"]: 
			print "Cleaning chroot: "+x+"... "
			cmd("rm -rf "+self.settings["destpath"]+x,"Couldn't clean "+x,env=self.env)

		# put /etc/hosts back into place
		if os.path.exists(self.settings["chroot_path"]+"/etc/hosts.bck"):
			cmd("mv -f "+self.settings["chroot_path"]+"/etc/hosts.bck "+self.settings["chroot_path"]+"/etc/hosts", "Could not replace /etc/hosts",env=self.env)

		# clean up old and obsoleted files in /etc
		if os.path.exists(self.settings["stage_path"]+"/etc"):
			cmd("find "+self.settings["stage_path"]+"/etc -maxdepth 1 -name \"*-\" | xargs rm -f", "Could not remove stray files in /etc",env=self.env)

		if os.path.exists(self.settings["controller_file"]):
			cmd("/bin/bash "+self.settings["controller_file"]+" clean","clean script failed.",env=self.env)
	
	def empty(self):		
		if self.settings.has_key(self.settings["target"]+"/empty"):
		    if type(self.settings[self.settings["target"]+"/empty"])==types.StringType:
			self.settings[self.settings["target"]+"/empty"]=self.settings[self.settings["target"]+"/empty"].split()
		    for x in self.settings[self.settings["target"]+"/empty"]:
			myemp=self.settings["destpath"]+x
			if not os.path.isdir(myemp):
			    print x,"not a directory or does not exist, skipping 'empty' operation."
			    continue
			print "Emptying directory",x
			# stat the dir, delete the dir, recreate the dir and set
			# the proper perms and ownership
			mystat=os.stat(myemp)
			shutil.rmtree(myemp)
			os.makedirs(myemp,0755)
			os.chown(myemp,mystat[ST_UID],mystat[ST_GID])
			os.chmod(myemp,mystat[ST_MODE])
	
	def remove(self):
		if self.settings.has_key(self.settings["target"]+"/rm"):
		    for x in self.settings[self.settings["target"]+"/rm"]:
			# we're going to shell out for all these cleaning operations,
			# so we get easy glob handling
			print "livecd: removing "+x
			os.system("rm -rf "+self.settings["chroot_path"]+x)
		try:
		    if os.path.exists(self.settings["controller_file"]):
			    cmd("/bin/bash "+self.settings["controller_file"]+" clean",\
				"Clean  failed.",env=self.env)
		except:
		    self.unbind()
		    raise

	
	def preclean(self):
		try:
			if os.path.exists(self.settings["controller_file"]):
		    		cmd("/bin/bash "+self.settings["controller_file"]+" preclean","preclean script failed.",env=self.env)
		except:
			self.unbind()
			raise CatalystError, "Build failed, could not execute preclean"

	def capture(self):
		"""capture target in a tarball"""
		# IF TARGET EXISTS, REMOVE IT - WE WILL CREATE A NEW ONE
		if os.path.isfile(self.settings["target_path"]):
			cmd("rm -f "+self.settings["target_path"], "Could not remove existing file: "+self.settings["target_path"],env=self.env)
		mypath=self.settings["target_path"].split("/")
		# remove filename from path
		mypath=string.join(mypath[:-1],"/")
		# now make sure path exists
		if not os.path.exists(mypath):
			os.makedirs(mypath)
		print "Creating stage tarball..."
		cmd("tar cjpf "+self.settings["target_path"]+" -C "+self.settings["stage_path"]+" .","Couldn't create stage tarball",env=self.env,badval=2)

	def run_local(self):
		try:
			if os.path.exists(self.settings["controller_file"]):
		    		cmd("/bin/bash "+self.settings["controller_file"]+" run","run script failed.",env=self.env)

		except CatalystError:
			self.unbind()
			raise CatalystError,"Stage build aborting due to error."
	
	def setup_environment(self):
		# Modify the current environment. This is an ugly hack that should be
		# fixed. We need this to use the os.system() call since we can't
		# specify our own environ:
		for x in self.settings.keys():
			# sanitize var names by doing "s|/-.|_|g"
			varname="clst_"+string.replace(x,"/","_")
			varname=string.replace(varname,"-","_")
			varname=string.replace(varname,".","_")
			if type(self.settings[x])==types.StringType:
				# prefix to prevent namespace clashes:
				#os.environ[varname]=self.settings[x]
				self.env[varname]=self.settings[x]
			elif type(self.settings[x])==types.ListType:
				#os.environ[varname]=string.join(self.settings[x])
				self.env[varname]=string.join(self.settings[x])
			elif type(self.settings[x])==types.BooleanType:
				if self.settings[x]:
					self.env[varname]="true"
				else:
					self.env[varname]="false"
		if self.settings.has_key("makeopts"):
			self.env["MAKEOPTS"]=self.settings["makeopts"]
			
	
	def unmerge(self):
		if self.settings.has_key(self.settings["target"]+"/unmerge"):
		    if type(self.settings[self.settings["target"]+"/unmerge"])==types.StringType:
			self.settings[self.settings["target"]+"/unmerge"]=[self.settings[self.settings["target"]+"/unmerge"]]
		    myunmerge=self.settings[self.settings["target"]+"/unmerge"][:]
		    
		    for x in range(0,len(myunmerge)):
		    #surround args with quotes for passing to bash,
		    #allows things like "<" to remain intact
		        myunmerge[x]="'"+myunmerge[x]+"'"
		    myunmerge=string.join(myunmerge)
		    
		    #before cleaning, unmerge stuff:
		    try:
			cmd("/bin/bash "+self.settings["controller_file"]+" unmerge "+ myunmerge,\
				"Unmerge script failed.",env=self.env)
			#cmd("/bin/bash "+self.settings["sharedir"]+"/targets/" \
			#	+self.settings["target"]+"/unmerge.sh "+myunmerge,"Unmerge script failed.",env=self.env)
			print "unmerge shell script"
		    except CatalystError:
			self.unbind()
			raise

	def clear_dir(self,path):
	    if not os.path.isdir(path):
	    	return
		print "Emptying directory",path
		# stat the dir, delete the dir, recreate the dir and set the proper perms and ownership
		mystat=os.stat(path)
		if os.uname()[0] == "FreeBSD": # There's no easy way to change flags recursively in python
			os.system("chflags -R noschg "+path)
		shutil.rmtree(path)
		os.makedirs(path,0755)
		os.chown(path,mystat[ST_UID],mystat[ST_GID])
		os.chmod(path,mystat[ST_MODE])

	def clear_chroot(self):
		self.clear_dir(self.settings["chroot_path"])

	def purge(self):
		self.clear_chroot()

#vim: ts=4 sw=4 sta et sts=4 ai
