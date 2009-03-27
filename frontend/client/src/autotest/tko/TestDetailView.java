package autotest.tko;

import autotest.common.JsonRpcCallback;
import autotest.common.JsonRpcProxy;
import autotest.common.PaddedJsonRpcProxy;
import autotest.common.Utils;
import autotest.common.ui.DetailView;
import autotest.common.ui.NotifyManager;
import autotest.common.ui.RealHyperlink;

import com.google.gwt.json.client.JSONNumber;
import com.google.gwt.json.client.JSONObject;
import com.google.gwt.json.client.JSONString;
import com.google.gwt.json.client.JSONValue;
import com.google.gwt.user.client.ui.Composite;
import com.google.gwt.user.client.ui.DisclosureEvent;
import com.google.gwt.user.client.ui.DisclosureHandler;
import com.google.gwt.user.client.ui.DisclosurePanel;
import com.google.gwt.user.client.ui.FlexTable;
import com.google.gwt.user.client.ui.FlowPanel;
import com.google.gwt.user.client.ui.HTML;
import com.google.gwt.user.client.ui.Label;
import com.google.gwt.user.client.ui.Panel;
import com.google.gwt.user.client.ui.RootPanel;
import com.google.gwt.user.client.ui.ScrollPanel;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

class TestDetailView extends DetailView {
    private static final int NO_TEST_ID = -1;

    private static final JsonRpcProxy logLoadingProxy = 
        new PaddedJsonRpcProxy(Utils.RETRIEVE_LOGS_URL);

    private int testId = NO_TEST_ID;
    private String jobTag;
    private List<LogFileViewer> logFileViewers = new ArrayList<LogFileViewer>();
    private RealHyperlink logLink = new RealHyperlink("(view all logs)");

    private Panel logPanel;
    
    private class LogFileViewer extends Composite implements DisclosureHandler {
        private DisclosurePanel panel;
        private String logFilePath;

        private JsonRpcCallback rpcCallback = new JsonRpcCallback() {
            @Override
            public void onError(JSONObject errorObject) {
                super.onError(errorObject);
                String errorString = getErrorString(errorObject);
                if (errorString.equals("")) {
                    errorString = "Failed to load log "+ logFilePath;
                }
                setStatusText(errorString);
            }

            @Override
            public void onSuccess(JSONValue result) {
                handle(result);
            }
        };
        
        public LogFileViewer(String logFilePath, String logFileName) {
            this.logFilePath = logFilePath;
            panel = new DisclosurePanel(logFileName);
            panel.addEventHandler(this);
            panel.addStyleName("log-file-panel");
            initWidget(panel);
        }
        
        public void onOpen(DisclosureEvent event) {
            JSONObject params = new JSONObject();
            params.put("path", new JSONString(getLogUrl()));
            logLoadingProxy.rpcCall("dummy", params, rpcCallback);

            setStatusText("Loading...");
        }

        private String getLogUrl() {
            return Utils.getLogsUrl(jobTag + "/" + logFilePath);
        }
        
        public void handle(JSONValue value) {
            String logContents = value.isString().stringValue();
            if (logContents.equals("")) {
                setStatusText("Log file is empty");
            } else {
                setLogText(logContents);
            }
        }

        private void setLogText(String text) {
            panel.clear();
            Label label = new Label(text);
            ScrollPanel scroller = new ScrollPanel();
            scroller.add(label);
            panel.add(scroller);
        }
        
        private void setStatusText(String status) {
            panel.clear();
            panel.add(new HTML("<i>" + status + "</i>"));
        }

        public void onClose(DisclosureEvent event) {}
    }
    
    private static class AttributeTable extends Composite {
        private DisclosurePanel container = new DisclosurePanel("Test attributes");
        private FlexTable table = new FlexTable();
        
        public AttributeTable(JSONObject attributes) {
            processAttributes(attributes);
            setupTableStyle();
            container.add(table);
            initWidget(container);
        }

        private void processAttributes(JSONObject attributes) {
            if (attributes.size() == 0) {
                table.setText(0, 0, "No test attributes");
                return;
            }
            
            List<String> sortedKeys = new ArrayList<String>(attributes.keySet());
            Collections.sort(sortedKeys);
            for (String key : sortedKeys) {
                String value = Utils.jsonToString(attributes.get(key));
                int row = table.getRowCount();
                table.setText(row, 0, key);
                table.setText(row, 1, value);
            }
        }
        
        private void setupTableStyle() {
            container.addStyleName("test-attributes");
        }
    }

    @Override
    public void initialize() {
        super.initialize();
        
        logPanel = new FlowPanel();
        RootPanel.get("td_log_files").add(logPanel);
        
        logLink.setOpensNewWindow(true);
        RootPanel.get("td_view_logs_link").add(logLink);
    }

    private void addLogViewers(String testName) {
        logPanel.clear();
        addLogFileViewer(testName + "/debug/stdout", "Test stdout");
        addLogFileViewer(testName + "/debug/stderr", "Test stderr");
        addLogFileViewer("status.log", "Job status log");
        addLogFileViewer("debug/autoserv.stdout", "Job autoserv stdout");
        addLogFileViewer("debug/autoserv.stderr", "Job autoserv stderr");
    }

    private void addLogFileViewer(String logPath, String logName) {
        LogFileViewer viewer = new LogFileViewer(logPath, logName);
        logFileViewers.add(viewer);
        logPanel.add(viewer);
    }

    @Override
    protected void fetchData() {
        JSONObject params = new JSONObject();
        params.put("test_idx", new JSONNumber(testId));
        rpcProxy.rpcCall("get_detailed_test_views", params, new JsonRpcCallback() {
            @Override
            public void onSuccess(JSONValue result) {
                JSONObject test;
                try {
                    test = Utils.getSingleValueFromArray(result.isArray()).isObject();
                }
                catch (IllegalArgumentException exc) {
                    NotifyManager.getInstance().showError("No such job found");
                    resetPage();
                    return;
                }
                
                showTest(test);
            }
            
            @Override
            public void onError(JSONObject errorObject) {
                super.onError(errorObject);
                resetPage();
            }
        });
    }
    
    @Override
    protected void setObjectId(String id) {
        try {
            testId = Integer.parseInt(id);
        }
        catch (NumberFormatException exc) {
            throw new IllegalArgumentException();
        }
    }
    
    @Override
    protected String getObjectId() {
        if (testId == NO_TEST_ID) {
            return NO_OBJECT;
        }
        return Integer.toString(testId);
    }

    @Override
    protected String getDataElementId() {
        return "td_data";
    }

    @Override
    protected String getFetchControlsElementId() {
        return "td_fetch_controls";
    }

    @Override
    protected String getNoObjectText() {
        return "No test selected";
    }

    @Override
    protected String getTitleElementId() {
        return "td_title";
    }

    @Override
    public String getElementId() {
        return "test_detail_view";
    }
    
    @Override
    public void display() {
        super.display();
        CommonPanel.getPanel().setConditionVisible(false);
    }

    protected void showTest(JSONObject test) {
        String testName = test.get("test_name").isString().stringValue();
        jobTag = test.get("job_tag").isString().stringValue();
        
        showText(testName, "td_test");
        showText(jobTag, "td_job_tag");
        showField(test, "job_name", "td_job_name");
        showField(test, "status", "td_status");
        showField(test, "reason", "td_reason");
        showField(test, "test_started_time", "td_test_started");
        showField(test, "test_finished_time", "td_test_finished");
        showField(test, "hostname", "td_hostname");
        showField(test, "platform", "td_platform");
        showField(test, "kernel", "td_kernel");
        
        String[] labels = Utils.JSONtoStrings(test.get("labels").isArray());
        String labelList = Utils.joinStrings(", ", Arrays.asList(labels));
        if (labelList.equals("")) {
            labelList = "none";
        }
        showText(labelList, "td_test_labels");
        
        JSONObject attributes = test.get("attributes").isObject();
        RootPanel attributePanel = RootPanel.get("td_attributes");
        attributePanel.clear();
        attributePanel.add(new AttributeTable(attributes));
        
        logLink.setHref(Utils.getRetrieveLogsUrl(jobTag));
        addLogViewers(testName);
        
        displayObjectData("Test " + testName + " (job " + jobTag + ")");
    }
    @Override
    public void resetPage() {
        super.resetPage();
    }
}
