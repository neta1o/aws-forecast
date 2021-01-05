import json
import boto3
import datetime
from dateutil.relativedelta  import relativedelta as rd
#Permissions required: AmazonSNSFullAccess(if using SNS),AWSOrganizationsReadOnlyAccess,AWSBillingReadOnlyAccess,ce:GetCostForecast & ce:GetCostAndUsage
#Make sure to set Lambda timeout to a larger time if there are a significant number of sub accounts
#Script is currently missing error catching logic
#Can create CloudWatch event rule to trigger the Lambda on a schedule ie 5th of every month at 8am Cron ex/ 0 8 5 * ? *

#https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ce.html#CostExplorer.Client.get_cost_forecast
#https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ce.html#CostExplorer.Client.get_cost_and_usage
#https://docs.aws.amazon.com/code-samples/latest/catalog/python-sns-sns-python-example-publish-to-topic.py.html

def lambda_handler(event, context):
    useSNS = False
    myARN = 'YOUR SNS ARN HERE'
    monthsPast = 2 #past months (current month counts as 1 and will not display)
    monthsFuture = 2 #future months (how many months past current month?)
    calYear = True #if this is False it'll use the monthsPast and monthsFuture values above, if True it'll use the calendar year
    
    accountBlock = {}
    custAccounts = []
    myToken = ''
    
    custOrg = boto3.client('organizations')
    accountBlock = custOrg.list_accounts(MaxResults=1)
    custAccounts.append(accountBlock)
    
    client = boto3.client('ce')
    sns = boto3.client('sns')
    
    if calYear: #using calendar year so override monthsPast and monthsFuture
        if datetime.datetime.today().strftime('%m') == '01': #set monthsPast based on current date, if Jan go two months back to show Dec actual
                monthsPast=2
        else:
                monthsPast=int(datetime.datetime.today().strftime('%m'))
        if datetime.datetime.today().strftime('%m') == 12: #set monthsFuture based on current date
                monthsFuture=1
        else:
                monthsFuture=12-int(datetime.datetime.today().strftime('%m'))

    use_date = datetime.datetime.today()
    use_date_future = use_date+rd(months=+monthsFuture)+rd(day=31)+rd(days=+1) #first day x months ahead
    use_date_past = use_date+rd(months=-int(monthsPast))+rd(day=31)+rd(days=+1) #first day x months ahead
    output = ("Forecast run on " + datetime.datetime.today().strftime('%m/%d/%Y') + " for dates " + 
        use_date_past.strftime('%m/%d/%Y') + "-" + use_date_future.strftime('%m/%d/%Y') + "\n" + "Account Name,Account Number")
    
    m=0
    while m<(int(monthsPast)-1): #loop months past and concatenate to output, -1 to not show current
        output = output + "," + (use_date+rd(months=-int(monthsPast-(m+1)))).strftime('%m/%Y')
        m+=1

    m=0
    while m<=int(monthsFuture): #loop months future to concatenate to output
        output = output + ",*" + (use_date+rd(months=+int(m))).strftime('%m/%Y')
        m+=1
    
    while True:
        myToken = accountBlock.get("NextToken") #this will be blank on last loop

        if myToken is not None:
            myToken = accountBlock['NextToken']
            accountBlock = custOrg.list_accounts(MaxResults=1,NextToken=myToken)
            custAccounts.append(accountBlock)
        else: 
            aLength = len(custAccounts)
            i=0
            while i<aLength: #loop customer sub accounts
                output = output + "\n" + custAccounts[i]['Accounts'][0]['Name'] + "," + custAccounts[i]['Accounts'][0]['Id']
                response_future = client.get_cost_forecast(
                    TimePeriod={
                        'Start': datetime.datetime.today().strftime('%Y-%m-%d') , 
                        'End': use_date_future.strftime('%Y-%m-%d') 
                    },
                    Metric='UNBLENDED_COST',
                    Granularity='MONTHLY',
                        Filter={
                        'Dimensions': { 'Key': 'LINKED_ACCOUNT', 'Values': [ custAccounts[i]['Accounts'][0]['Id'] ]
                        }
                    },
                )
                response_past = client.get_cost_and_usage(
                    TimePeriod={
                        'Start': use_date_past.strftime('%Y-%m-%d'), 
                        'End': datetime.datetime.today().strftime('%Y-%m-%d')
                    },
                    Metrics=['UnblendedCost'],
                    Granularity='MONTHLY',
                        Filter={
                        'Dimensions': { 'Key': 'LINKED_ACCOUNT', 'Values': [ custAccounts[i]['Accounts'][0]['Id'] ]
                        }
                    },
                )
                ##print(response_past['ResultsByTime'])
                pLen = len(response_past['ResultsByTime'])
                myp=0
                while myp<(pLen-1): #loop past and current number
                    output = output + ",$" + str(round(float(response_past['ResultsByTime'][myp]['Total']['UnblendedCost']['Amount']),2)) #concatenate each months historic values
                    myp=myp+1
                #output = output + "|"
                fLen = len(response_future['ForecastResultsByTime'])
                myi=0
                while myi<(fLen): #loop future forecast numbers
                    output = output + ",*$" + str(round(float(response_future['ForecastResultsByTime'][myi]['MeanValue']),2)) #concatenate each months forecast values
                    myi=myi+1
                i=i+1
            print(output)
            if useSNS:
                snsResponse = sns.publish(
                    TopicArn=myARN,
                    Message=output,
                )
                print(snsResponse)
            break;
    return {
       'statusCode': 200,
      'body': json.dumps('-----DONE-----')
    }
    
###NOTES
    #print(response['ForecastResultsByTime'][myi])
    #output = output + custAccounts[i]['Accounts'][0]['Id'] + "," + custAccounts[i]['Accounts'][0]['Name'] + "," +  
    #response['ForecastResultsByTime'][myi]['TimePeriod']['Start'] + "," + response['ForecastResultsByTime'][myi]['TimePeriod']['End'] + ",$" + 
    #str(round(float(response['ForecastResultsByTime'][myi]['MeanValue']),2)) + "\n"
    #print(custAccounts[i]['Accounts']) #Full Account Information
