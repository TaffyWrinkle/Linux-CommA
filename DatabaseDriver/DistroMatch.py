import pyodbc
from DatabaseDriver.DatabaseDriver import DatabaseDriver

class DistroMatch(DatabaseDriver):
    
    def __init__(self):
        '''Initializa database connection'''
        super.__init__()
    
    def insertInto(self,DistroPatchMatch, patchId, distroId, commitId, date):
        '''
        Insert data into upstream_patchtracker
        '''
        conx = self.cursor.execute("insert into [dbo].[DistributionPatches]\
            ([patchId],[distroId],[commitId],[bugReportLink],[datetimeAdded],[authorMatch],[subjectMatch],[descriptionMatch],[codeMatch],[fileNameMatch],[confidence])\
                values(?,?,?,?,?,?,?,?)",\
                    patchId,distroId,commitId, "",date,DistroPatchMatch.author_confidence,DistroPatchMatch.subject_confidence,DistroPatchMatch.description_confidence,DistroPatchMatch.filename_confidence,DistroPatchMatch.confidence)
        conx.commit()
    
    def checkIfPresent(self, commit_id):
        """
        Check if commit is already present in database
        """
        rows = self.cursor.execute("SELECT * from [DistributionPatches] where commitId like ?;",commit_id).fetchall()
        if rows is None or len(rows) == 0:
            return False
        else:
            return True