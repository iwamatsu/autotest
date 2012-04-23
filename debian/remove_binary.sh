git checkout $1
find client/tests/ -name *.gz -print | xargs rm 
find client/tests/ -name *.tgz -print | xargs rm
find client/tests/ -name *.bz2 -print | xargs rm
find client/tests/ -name *.tar -print | xargs rm
git commit -asm "Remove binary data"
git tag $1+dfsg 
git checkout debian
git rebase $1+dfsg
